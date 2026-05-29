"""
Security Agent
==============
Performs comprehensive security assessment of codebases.
Scans for vulnerabilities, hardcoded secrets, dependency risks,
and OWASP Top 10 violations. Reports security score and findings.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from pathlib import Path
from typing import Optional

from agents.base_agent import (
    AgentInput,
    AgentOutput,
    BaseAgent,
)
from agents.prompts.load_prompt import load_prompt
from core.logging_utils import log_suppressed
from llm import GenerationConfig, LLMRouter
from llm.factory_defaults import FACTORY_MAX_OUTPUT_TOKENS_HEAVY, FACTORY_TIMEOUT_QA_SEC

logger = logging.getLogger(__name__)

SECURITY_SYSTEM_PROMPT = load_prompt("security_system_prompt.md")


class SecurityAgent(BaseAgent):
    """Security Agent - performs security assessment of code."""

    def __init__(self, llm_router: LLMRouter):
        super().__init__(
            agent_type="security",
            llm_router=llm_router,
            task_type="security_scan",
        )

    async def execute(self, agent_input: AgentInput) -> AgentOutput:
        """Execute security assessment on the product's codebase."""
        start_time = time.time()
        product_id = agent_input.product_id
        code_data = agent_input.data.get("code_data", {})

        self._log("INFO", f"Running security assessment for {product_id}")

        try:
            # Step 1: Discover code files
            code_files = self._discover_code_files(product_id)
            self._log("INFO", f"Found {len(code_files)} code files for security scan")

            # Step 2: Static security analysis (no LLM needed)
            static_findings = self._run_static_security_scan(code_files)
            self._log("INFO", f"Static scan found {len(static_findings)} issues")

            # Step 3: Secrets detection
            secrets_found = self._detect_secrets(code_files)
            self._log("INFO", f"Secrets scan found {len(secrets_found)} potential secrets")

            # Step 4: Dependency check
            dep_risks = self._check_dependency_risks(code_files)

            # Step 5: Calculate security score
            security_score = self._compute_security_score(
                static_findings, secrets_found, dep_risks
            )
            grade = self._score_to_grade(security_score)

            # Step 6: Try LLM review for deeper analysis
            llm_findings = await self._generate_llm_security_review(
                agent_input, product_id, code_files
            )

            # Merge LLM findings into our findings
            all_vulnerabilities = static_findings.copy()
            if llm_findings and "vulnerabilities" in llm_findings:
                existing_ids = {v.get("id", "") for v in all_vulnerabilities}
                for v in llm_findings.get("vulnerabilities", []):
                    v_id = v.get("id", f"sec-llm-{uuid.uuid4().hex[:8]}")
                    if v_id not in existing_ids:
                        if "id" not in v:
                            v["id"] = v_id
                        all_vulnerabilities.append(v)
                        existing_ids.add(v_id)

            # Determine passed/failed checks
            passed_checks = self._get_passed_checks(all_vulnerabilities)
            failed_checks = self._get_failed_checks(all_vulnerabilities)

            # Build output
            severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
            for v in all_vulnerabilities:
                sev = v.get("severity", "info")
                if sev in severity_counts:
                    severity_counts[sev] += 1

            output_data = {
                "security_score": security_score,
                "grade": grade,
                "vulnerabilities": all_vulnerabilities,
                "secrets_found": secrets_found,
                "dependency_risks": dep_risks,
                "passed_checks": passed_checks,
                "failed_checks": failed_checks,
                "summary": f"Security scan completed. Score: {security_score}/100 ({grade}). "
                           f"Found {len(all_vulnerabilities)} vulnerabilities "
                           f"({severity_counts['critical']} critical, {severity_counts['high']} high, "
                           f"{severity_counts['medium']} medium, {severity_counts['low']} low).",
                "severity_counts": severity_counts,
                "total_files_scanned": len(code_files),
            }

            # Save security report artifact
            self._save_artifact(
                product_id,
                "security",
                {
                    "report": output_data,
                    "scanned_at": time.time(),
                    "scanner_version": "1.0.0",
                },
                filename="security_report.json",
            )

            elapsed = time.time() - start_time
            self._log("INFO", f"Security assessment for {product_id} completed in {elapsed:.1f}s")

            return AgentOutput(
                task_id=agent_input.task_id,
                product_id=product_id,
                agent_type=self.agent_type,
                success=True,
                data=output_data,
                timestamp=time.time(),
                metrics={
                    "elapsed_seconds": round(elapsed, 2),
                    "files_scanned": len(code_files),
                    "vulnerabilities_found": len(all_vulnerabilities),
                    "secrets_found": len(secrets_found),
                    "security_score": security_score,
                },
            )

        except Exception as e:
            elapsed = time.time() - start_time
            self._log("ERROR", f"Security assessment failed for {product_id}: {e}")

            return AgentOutput(
                task_id=agent_input.task_id,
                product_id=product_id,
                agent_type=self.agent_type,
                success=False,
                data={
                    "error": str(e),
                    "security_score": 0,
                    "grade": "F",
                    "summary": f"Security scan failed: {e}",
                },
                error=str(e),
                timestamp=time.time(),
                metrics={"elapsed_seconds": round(elapsed, 2), "files_scanned": 0},
            )

    def _discover_code_files(self, product_id: str) -> list[dict]:
        """Discover all code files for the product."""
        from core.paths import code_dir as product_code_dir

        code_dir = product_code_dir(product_id)
        files = []

        if not code_dir.exists():
            return files

        # Try loading code manifest first
        manifest_path = code_dir / "code_manifest.json"
        if manifest_path.exists():
            try:
                with open(manifest_path) as f:
                    manifest = json.load(f)
                raw_files = manifest.get("files", [])
                # Handle case where manifest stores STRING paths instead of dicts
                # (bug in dev.py saves file paths as strings, not dicts with content)
                if raw_files and isinstance(raw_files[0], str):
                    for filepath in raw_files:
                        path = Path(filepath)
                        if path.exists():
                            try:
                                content = path.read_text(encoding="utf-8", errors="ignore")[:5000]
                                files.append({
                                    "path": str(path.relative_to(code_dir)) if code_dir in path.parents else filepath,
                                    "full_path": str(path),
                                    "content": content,
                                })
                            except OSError as _suppressed_exc:
                                log_suppressed(logger, "non-fatal (agents/security.py)", exc_info=_suppressed_exc)
                    return files
                return raw_files
            except Exception as _suppressed_exc:
                log_suppressed(logger, "non-fatal (agents/security.py)", exc_info=_suppressed_exc)

        # Fallback: scan directory
        for ext in [".py", ".js", ".ts", ".jsx", ".tsx", ".yaml", ".yml", ".json", ".env", ".cfg", ".ini", ".conf", ".sh"]:
            for fpath in code_dir.rglob(f"*{ext}"):
                try:
                    content = fpath.read_text(encoding="utf-8", errors="ignore")[:5000]
                    files.append({
                        "path": str(fpath.relative_to(code_dir)),
                        "full_path": str(fpath),
                        "content": content,
                        "ext": ext,
                    })
                except Exception as _suppressed_exc:
                    log_suppressed(logger, "non-fatal (agents/security.py)", exc_info=_suppressed_exc)

        return files

    def _run_static_security_scan(self, code_files: list[dict]) -> list[dict]:
        """Run static analysis for common security issues."""
        findings = []

        # Security patterns to detect (category -> list of (pattern, severity, description, recommendation))
        security_patterns = {
            "sql_injection": [
                (r'execute\s*\(\s*["\']\s*SELECT', "critical",
                 "Possible SQL injection via direct string concatenation in execute()",
                 "Use parameterized queries or an ORM instead of string concatenation"),
                (r'cursor\.execute\s*\(\s*f["\']', "critical",
                 "SQL query built with f-string - possible injection risk",
                 "Use parameterized queries with ? or %s placeholders"),
                (r'raw\(.*["\']', "high",
                 "Raw SQL query detected - potential injection vector",
                 "Use ORM query builder or parameterized queries"),
            ],
            "command_injection": [
                (r'os\.system\s*\(', "critical",
                 "Shell command execution via os.system() - command injection risk",
                 "Use subprocess.run() with argument list instead of shell=True"),
                (r'subprocess\.(call|Popen|run)\s*\(.*shell\s*=\s*True', "critical",
                 "Shell execution with shell=True - command injection risk",
                 "Pass command as list and avoid shell=True"),
                (r'eval\s*\(', "critical",
                 "eval() detected - arbitrary code execution risk",
                 "Avoid eval(). Use ast.literal_eval() or safer alternatives"),
                (r'exec\s*\(', "critical",
                 "exec() detected - arbitrary code execution risk",
                 "Avoid exec(). Use safer alternatives"),
                (r'pickle\.loads?\s*\(', "high",
                 "Pickle deserialization - arbitrary code execution risk",
                 "Use safer serialization like JSON or PyYAML safe_load"),
            ],
            "hardcoded_secrets": [
                (r'(?i)(api[_-]?key|apikey|api_key)\s*[=:]\s*["\'][^"\'\s]{8,}', "high",
                 "Possible hardcoded API key",
                 "Move to environment variables or secrets manager"),
                (r'(?i)(secret|token|password|passwd|pwd)\s*[=:]\s*["\'][^"\'\s]{8,}', "high",
                 "Possible hardcoded secret/token/password",
                 "Move to environment variables or secrets manager"),
                (r'(?i)(aws_access_key_id|aws_secret_access_key|AKIA[0-9A-Z]{16})', "critical",
                 "AWS credential detected in code",
                 "Remove from code. Use IAM roles or environment variables"),
                (r'(?i)(-----BEGIN (RSA )?PRIVATE KEY-----)', "critical",
                 "Private key detected in code",
                 "Remove from code immediately. Use proper key management"),
                (r'(?i)(ghp_|gho_|github_pat_)[0-9a-zA-Z]{36}', "critical",
                 "GitHub token detected in code",
                 "Revoke token immediately and use environment variables"),
                (r'(?i)(sk-[a-zA-Z0-9]{32,})', "high",
                 "Possible OpenAI/API key detected",
                 "Move to environment variables"),
                (r'(?i)(mongodb\+srv://[^@]+@)', "critical",
                 "MongoDB connection string with credentials",
                 "Use environment variables for connection strings"),
                (r'(?i)(postgresql?://[^:]+:[^@]+@)', "critical",
                 "Database connection string with password",
                 "Use environment variables for connection strings"),
            ],
            "xss_vulnerability": [
                (r'dangerouslySetInnerHTML', "critical",
                 "dangerouslySetInnerHTML detected - XSS risk in React",
                 "Use sanitized React rendering or DOMPurify"),
                (r'innerHTML\s*=', "high",
                 "innerHTML assignment - XSS risk",
                 "Use textContent or innerText instead"),
                (r'v-html\s*=', "high",
                 "v-html detected - XSS risk in Vue",
                 "Use template interpolation instead"),
                (r'\.html\s*\(', "high",
                 ".html() jQuery call - XSS risk",
                 "Use .text() or sanitize input first"),
            ],
            "insecure_crypto": [
                (r'md5\s*\(', "medium",
                 "MD5 hash detected - cryptographically broken",
                 "Use SHA-256 or higher for hashing"),
                (r'sha1\s*\(', "medium",
                 "SHA-1 hash detected - cryptographically weakened",
                 "Use SHA-256 or higher"),
                (r'DES[^C]', "medium",
                 "DES encryption detected - obsolete and insecure",
                 "Use AES-256-GCM or similar modern encryption"),
            ],
            "information_disclosure": [
                (r'DEBUG\s*=\s*True', "medium",
                 "Debug mode enabled in production",
                 "Set DEBUG=False in production"),
                (r'ALLOWED_HOSTS\s*=\s*\["\*"\]', "medium",
                 "CORS/ALLOWED_HOSTS set to wildcard",
                 "Restrict to specific hosts in production"),
                (r'print\s*\(\s*.*(?:password|secret|token|key)', "medium",
                 "Printing sensitive data to stdout",
                 "Remove print statements for sensitive data"),
            ],
            "path_traversal": [
                (r'open\s*\(\s*f["\']\s*\.\.?/', "high",
                 "Path traversal possible via user-controlled file path",
                 "Validate and sanitize all file paths"),
                (r'\.\.\/', "high",
                 "Directory traversal pattern detected",
                 "Use path validation to prevent traversal attacks"),
            ],
            "insecure_config": [
                (r'CORS_ORIGIN_ALLOW_ALL\s*=\s*True', "medium",
                 "CORS allowing all origins",
                 "Restrict CORS to specific origins"),
                (r'SECRET_KEY\s*=\s*["\'][a-zA-Z0-9]{1,16}["\']', "high",
                 "Weak SECRET_KEY - too short",
                 "Use a strong, long random secret key"),
                (r'ssl_verify\s*=\s*False', "high",
                 "SSL verification disabled",
                 "Enable SSL verification"),
            ],
        }

        for file_info in code_files:
            content = file_info.get("content", "")
            filepath = file_info.get("path", "")

            for category, patterns in security_patterns.items():
                for pattern, severity, description, recommendation in patterns:
                    try:
                        matches = re.finditer(pattern, content)
                        for match in matches:
                            # Get context around the match
                            start = max(0, match.start() - 40)
                            end = min(len(content), match.end() + 40)
                            context = content[start:end]

                            findings.append({
                                "id": f"sec-{uuid.uuid4().hex[:8]}",
                                "severity": severity,
                                "category": category,
                                "file": filepath,
                                "description": description,
                                "recommendation": recommendation,
                                "matched_pattern": match.group()[:80],
                                "context": context.strip(),
                                "source": "static_analysis",
                            })
                    except re.error as _suppressed_exc:
                        log_suppressed(logger, "non-fatal (agents/security.py)", exc_info=_suppressed_exc)

        return findings

    def _detect_secrets(self, code_files: list[dict]) -> list[dict]:
        """Detect potential hardcoded secrets in code."""
        secrets = []
        high_entropy_pattern = re.compile(r'[A-Za-z0-9+/]{32,}={0,2}')

        entropy_sensitive_exts = {".py", ".js", ".ts", ".env", ".json", ".yaml", ".yml", ".cfg", ".ini", ".conf"}

        for file_info in code_files:
            content = file_info.get("content", "")
            filepath = file_info.get("path", "")
            ext = file_info.get("ext", "")

            # Skip certain file types
            if ext in {".json"} and "package" in filepath.lower():
                continue
            if ext in {".json"} and "lock" in filepath.lower():
                continue

            # Check for high entropy strings in sensitive files
            if ext in entropy_sensitive_exts:
                lines = content.split("\n")
                for i, line in enumerate(lines):
                    # Skip comments and imports
                    stripped = line.strip()
                    if stripped.startswith(("#", "//", "/*")):
                        continue
                    if "import " in stripped or "from " in stripped:
                        continue

                    # Check for base64-like high entropy strings
                    matches = high_entropy_pattern.findall(stripped)
                    for match in matches:
                        # Calculate entropy
                        if self._calc_entropy(match) > 4.0:
                            secrets.append({
                                "type": "high_entropy_string",
                                "file": filepath,
                                "line": i + 1,
                                "context": stripped[:120],
                                "length": len(match),
                                "entropy": round(self._calc_entropy(match), 2),
                            })

        return secrets

    def _calc_entropy(self, s: str) -> float:
        """Calculate Shannon entropy of a string."""
        if not s:
            return 0.0
        entropy = 0.0
        length = len(s)
        for c in set(s):
            freq = s.count(c) / length
            if freq > 0:
                entropy -= freq * (freq and __import__("math").log2(freq))
        return entropy

    def _check_dependency_risks(self, code_files: list[dict]) -> list[dict]:
        """Check for dependency risks."""
        risks = []

        for file_info in code_files:
            content = file_info.get("content", "")
            filepath = file_info.get("path", "")

            # Check requirements.txt
            if filepath.endswith("requirements.txt"):
                for line in content.split("\n"):
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "==" in line:
                        pkg, ver = line.split("==", 1)
                        pkg = pkg.strip().lower()
                        ver = ver.strip()
                        # Known vulnerable versions (heuristic)
                        if pkg == "django" and ver.startswith("1"):
                            risks.append({
                                "package": f"django=={ver}",
                                "issue": "Django 1.x is end-of-life with known vulnerabilities",
                                "severity": "high",
                            })
                        if pkg == "flask" and ver.startswith("0"):
                            risks.append({
                                "package": f"flask=={ver}",
                                "issue": "Flask 0.x is outdated",
                                "severity": "medium",
                            })
                        if pkg in ("pyyaml", "yaml") and ver.startswith("4"):
                            risks.append({
                                "package": f"{pkg}=={ver}",
                                "issue": "Known deserialization vulnerability in PyYAML < 5.1",
                                "severity": "high",
                            })

            # Check package.json
            if filepath.endswith("package.json"):
                try:
                    pkg_data = json.loads(content)
                    for section in ["dependencies", "devDependencies"]:
                        deps = pkg_data.get(section, {})
                        for pkg_name, ver in deps.items():
                            ver_str = str(ver)
                            if pkg_name == "lodash" and ver_str.startswith("^4.17."):
                                # Check if below 4.17.21
                                try:
                                    patch = int(ver_str.split(".")[-1].replace("^", "").replace("~", ""))
                                    if patch < 21:
                                        risks.append({
                                            "package": f"lodash@{ver_str}",
                                            "issue": "lodash < 4.17.21 has prototype pollution vulnerability",
                                            "severity": "high",
                                        })
                                except ValueError as _suppressed_exc:
                                    log_suppressed(logger, "non-fatal (agents/security.py)", exc_info=_suppressed_exc)
                except (json.JSONDecodeError, Exception) as _suppressed_exc:
                    log_suppressed(logger, "non-fatal (agents/security.py)", exc_info=_suppressed_exc)

        return risks

    def _compute_security_score(
        self, findings: list[dict], secrets: list[dict], dep_risks: list[dict]
    ) -> int:
        """Compute overall security score (0-100)."""
        score = 100

        # Deduct for vulnerabilities based on severity
        severity_deductions = {
            "critical": 25,
            "high": 15,
            "medium": 8,
            "low": 3,
            "info": 1,
        }

        for finding in findings:
            sev = finding.get("severity", "info")
            deduction = severity_deductions.get(sev, 1)
            score -= deduction

        # Deduct for secrets found
        score -= len(secrets) * 10

        # Deduct for dependency risks
        for risk in dep_risks:
            sev = risk.get("severity", "medium")
            deduction = severity_deductions.get(sev, 5)
            score -= deduction

        return max(0, min(100, score))

    def _score_to_grade(self, score: int) -> str:
        if score >= 90:
            return "A"
        elif score >= 75:
            return "B"
        elif score >= 55:
            return "C"
        elif score >= 35:
            return "D"
        else:
            return "F"

    def _get_passed_checks(self, findings: list[dict]) -> list[str]:
        """Determine which security checks passed."""
        all_categories = {
            "sql_injection": "SQL Injection Prevention",
            "command_injection": "Command Injection Prevention",
            "hardcoded_secrets": "No Hardcoded Secrets",
            "xss_vulnerability": "XSS Prevention",
            "insecure_crypto": "Use of Secure Cryptography",
            "information_disclosure": "No Information Disclosure",
            "path_traversal": "Path Traversal Prevention",
            "insecure_config": "Secure Configuration",
        }

        failed_categories = {f.get("category", "") for f in findings}
        passed = []
        for cat, name in all_categories.items():
            if cat not in failed_categories:
                passed.append(name)
            else:
                # Check if only low/info severity
                cat_findings = [f for f in findings if f.get("category") == cat]
                if all(f.get("severity") in ("low", "info") for f in cat_findings):
                    passed.append(name)

        return passed

    def _get_failed_checks(self, findings: list[dict]) -> list[str]:
        """Determine which security checks failed."""
        all_categories = {
            "sql_injection": "SQL Injection Prevention",
            "command_injection": "Command Injection Prevention",
            "hardcoded_secrets": "No Hardcoded Secrets",
            "xss_vulnerability": "XSS Prevention",
            "insecure_crypto": "Use of Secure Cryptography",
            "information_disclosure": "No Information Disclosure",
            "path_traversal": "Path Traversal Prevention",
            "insecure_config": "Secure Configuration",
        }

        failed = []
        for cat, name in all_categories.items():
            cat_findings = [f for f in findings if f.get("category") == cat]
            if cat_findings:
                has_serious = any(f.get("severity") in ("critical", "high", "medium") for f in cat_findings)
                if has_serious:
                    failed.append(name)

        return failed

    async def _generate_llm_security_review(
        self, agent_input: AgentInput, product_id: str, code_files: list[dict]
    ) -> dict | None:
        """Try to generate an LLM-based security review if LLM is available."""
        try:
            code_samples = {}
            for file_info in code_files[:10]:
                code_samples[file_info["path"]] = file_info["content"][:2000]

            code_str = json.dumps(code_samples, indent=2) if code_samples else "No code files found"

            prompt = f"""{SECURITY_SYSTEM_PROMPT}

Product ID: {product_id}

Code Files:
{code_str}

Perform a thorough security audit of this codebase.
Focus on finding vulnerabilities, hardcoded secrets, and security issues.
"""

            config = GenerationConfig(
                temperature=0.3,
                max_tokens=FACTORY_MAX_OUTPUT_TOKENS_HEAVY,
                timeout_sec=FACTORY_TIMEOUT_QA_SEC,
                json_mode=True,  # openai_compatible skips response_format for reasoning models
            )

            response = await self._generate(prompt, config=config, agent_input=agent_input)

            result = self._extract_json(response)
            if result is not None:
                return result
        except Exception as _suppressed_exc:
            log_suppressed(logger, "non-fatal (agents/security.py)", exc_info=_suppressed_exc)

        return None
