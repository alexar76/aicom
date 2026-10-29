"""Every shell script SKOPOS runs on a monitored host, in one place.

This module is the single source of truth for the remote command surface. Three
consumers read it and they must never drift apart:

* the SSH transport, which pipes a script straight into ``bash`` on the host;
* the forced-command wrapper (``skopos-collect``), generated from these very
  strings so a restricted key can only ever run what is listed here;
* the push agent (``skopos-node``), which runs them locally and ships the output.

Keep the scripts POSIX-ish and defensive: they run on hosts we do not control,
under a user that should hold the least privilege that still answers the
question. Every script prints ``===SECTION===`` banners the parsers split on, so
changing a banner is a breaking change for the parser that consumes it.
"""

from __future__ import annotations

PROBE = r"""
set +e
echo '===META==='
hostname 2>/dev/null
uname -a 2>/dev/null
uptime 2>/dev/null
echo '===CPU==='
grep '^cpu ' /proc/stat 2>/dev/null
nproc 2>/dev/null
top -bn1 2>/dev/null | head -3
echo '===MEM==='
free -m 2>/dev/null
echo '===DISK==='
df -hP 2>/dev/null | head -20
echo '===NET==='
cat /proc/net/dev 2>/dev/null | head -20
echo '===LOAD==='
cat /proc/loadavg 2>/dev/null
echo '===PORTS==='
(ss -tulnp 2>/dev/null || netstat -tulnp 2>/dev/null) | head -80
echo '===FIREWALL==='
(ufw status verbose 2>/dev/null || iptables -L INPUT -n -v 2>/dev/null | head -15)
echo '===AUTH==='
(last -n 8 2>/dev/null; grep -h "Failed password" /var/log/auth.log /var/log/secure 2>/dev/null | tail -8)
echo '===DOCKER==='
echo '__PS__'
docker ps -a --format '{{.Names}}|{{.Image}}|{{.Status}}|{{.State}}|{{.Ports}}' 2>/dev/null | head -40
echo '__SKOPOS__'
docker stats --no-stream --format '{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}|{{.MemPerc}}|{{.NetIO}}|{{.BlockIO}}|{{.PIDs}}' 2>/dev/null | head -40
echo '__META__'
for cid in $(docker ps -aq 2>/dev/null | head -40); do
  docker inspect -f '{{.Name}}|{{index .Config.Labels "com.docker.compose.service"}}|{{index .Config.Labels "com.docker.compose.project"}}|{{.Config.Hostname}}' "$cid" 2>/dev/null
done
echo '===USERS==='
(getent passwd root 2>/dev/null; awk -F: '$3==0 {print}' /etc/passwd 2>/dev/null)
echo '===FAIL2BAN==='
echo '__SERVICE__'
systemctl is-active fail2ban 2>/dev/null || echo inactive
echo '__STATUS__'
fail2ban-client status 2>/dev/null | head -30
echo '__SSHD__'
fail2ban-client status sshd 2>/dev/null | head -30
echo '__LOG__'
for f in /var/log/fail2ban.log /var/log/fail2ban/fail2ban.log; do
  [ -r "$f" ] && tail -8 "$f" 2>/dev/null
done
echo '===SSHD==='
grep -E '^(PermitRootLogin|PasswordAuthentication|Port) ' /etc/ssh/sshd_config 2>/dev/null
"""


PORT_KNOCKS = r"""
set +e
echo '===AUTH==='
for f in /var/log/auth.log /var/log/secure; do
  [ -r "$f" ] && grep -hE "Failed password|Invalid user|Connection closed by|Disconnected from authenticating user|Did not receive identification" "$f" 2>/dev/null
done | tail -1000
echo '===UFW==='
for f in /var/log/ufw.log /var/log/kern.log /var/log/syslog; do
  [ -r "$f" ] && grep -h "UFW BLOCK" "$f" 2>/dev/null
done | tail -600
echo '===KERNEL==='
for f in /var/log/kern.log /var/log/syslog /var/log/messages; do
  [ -r "$f" ] && grep -hE "SRC=[0-9]" "$f" 2>/dev/null | grep -iE "DROP|REJECT|BLOCK|DENIED" | grep "DPT="
done | tail -500
echo '===FAIL2BAN==='
for f in /var/log/fail2ban.log /var/log/fail2ban/fail2ban.log; do
  [ -r "$f" ] && grep -hE "Ban |Unban " "$f" 2>/dev/null
done | tail -300
"""


DISCOVER_DOCKER = r"""
set -euo pipefail
docker ps --format '{{.Names}}|{{.Ports}}' 2>/dev/null | while IFS='|' read -r name ports; do
  [ -n "$name" ] || continue
  [ -n "$ports" ] || continue
  case "$ports" in
    *"0.0.0.0:"*|*"[::]:"*) ;;
    *) continue ;;
  esac
  # Skip obvious non-HTTP services (DB, cache, raw TCP).
  case "$ports" in
    *":5432->"*|*":6379->"*|*":16380->"*|*":15433->"*|*":3306->"*|*":27017->"*) continue ;;
  esac
  # Require a typical HTTP(S) host port binding.
  if echo "$ports" | grep -qE '0\.0\.0\.0:(80|443|3000|8000|8080|8081|8787|8788|9080|9081|9082|9090|9195|18001)->|\[::\]:(80|443|3000|8000|8080|8081|8787|8788|9080|9081|9082|9090|9195|18001)->'; then
    echo "docker:$name"
  fi
done | sort -u
"""


DISCOVER_NGINX_LOGS = r"""
set -euo pipefail
paths=()

# 1) Parse nginx configs (active + available).
for d in /etc/nginx /etc/nginx/sites-enabled /etc/nginx/sites-available /etc/nginx/conf.d; do
  [ -d "$d" ] || continue
  while IFS= read -r line; do
    tok=$(echo "$line" | awk '{print $2}' | tr -d ';')
    [ -n "$tok" ] || continue
    case "$tok" in
      off|syslog:*|/dev/*|stderr) continue ;;
    esac
    paths+=("$tok")
  done < <(grep -RhE '^\s*access_log\s+' "$d" 2>/dev/null || true)
done

# 2) Common log locations.
for g in /var/log/nginx/access.log /var/log/nginx/*access*.log; do
  [ -r "$g" ] && paths+=("$g")
done

# An empty array under `set -u` is an "unbound variable" error on bash <4.4,
# so a host with no nginx/apache at all would abort here instead of simply
# reporting nothing found. Guard the expansion.
if [ ${#paths[@]} -gt 0 ]; then
  printf '%s\n' "${paths[@]}" | sort -u
fi
"""


DISCOVER_APACHE_LOGS = r"""
set -euo pipefail
paths=()

for d in \
  /etc/apache2 \
  /etc/apache2/sites-enabled \
  /etc/apache2/sites-available \
  /etc/apache2/conf-enabled \
  /etc/apache2/conf-available \
  /etc/httpd \
  /etc/httpd/conf \
  /etc/httpd/conf.d \
  /etc/httpd/conf.modules.d; do
  [ -d "$d" ] || continue
  while IFS= read -r line; do
    # CustomLog "<path>" <format>  |  TransferLog "<path>"
    tok=$(echo "$line" | sed -E 's/^\s*(CustomLog|TransferLog)\s+//I' | awk '{print $1}' | tr -d '"')
    [ -n "$tok" ] || continue
    case "$tok" in
      off|syslog:*|/dev/*|stderr|combined|common) continue ;;
      "|"*) continue ;;                 # piped logger — cannot tail a file
    esac
    # Expand the common ${APACHE_LOG_DIR} placeholder (Debian default).
    tok=${tok//\$\{APACHE_LOG_DIR\}//var/log/apache2}
    case "$tok" in
      /*) paths+=("$tok") ;;            # absolute only (skip relative ServerRoot paths)
    esac
  done < <(grep -RhE '^\s*(CustomLog|TransferLog)\s+' "$d" 2>/dev/null || true)
done

for g in \
  /var/log/apache2/access.log \
  /var/log/apache2/other_vhosts_access.log \
  /var/log/apache2/*access*.log \
  /var/log/httpd/access_log \
  /var/log/httpd/*access* \
  /usr/local/apache2/logs/access_log \
  /opt/metis/deploy/apache-test/logs/access_log; do
  [ -r "$g" ] && paths+=("$g")
done

# An empty array under `set -u` is an "unbound variable" error on bash <4.4,
# so a host with no nginx/apache at all would abort here instead of simply
# reporting nothing found. Guard the expansion.
if [ ${#paths[@]} -gt 0 ]; then
  printf '%s\n' "${paths[@]}" | sort -u
fi
"""


PING = "echo SKOPOS_SSH_OK && hostname && uptime"


def tail_file(path: str, lines: int) -> str:
    """Read the last ``lines`` of a log file. Caller must have validated ``path``."""
    import shlex

    return f"set -euo pipefail; tail -n {int(lines)} {shlex.quote(path)} 2>/dev/null || true"


def docker_logs(container: str, lines: int) -> str:
    """Read the last ``lines`` of a container's stdout. Caller must have validated ``container``."""
    import shlex

    return f"set -euo pipefail; docker logs --tail {int(lines)} {shlex.quote(container)} 2>&1 || true"
