ARG BASE
FROM ${BASE}
USER root
RUN --mount=type=bind,source=bundle,target=/verified,ro \
    set -eu; \
    test "$(dpkg --print-architecture)" = amd64; \
    sqv --keyring /usr/share/keyrings/debian-archive-keyring.gpg --signatures=2 \
        --output /tmp/publisher-Debian-Release --cleartext /verified/InRelease; \
    python /verified/verify-debian.py /verified /tmp/publisher-Debian-Release; \
    rm /tmp/publisher-Debian-Release; \
    dpkg -i /verified/libapt-pkg7.0_3.0.4_amd64.deb \
            /verified/apt_3.0.4_amd64.deb \
            /verified/zlib1g_1.3.dfsg+really1.3.1-1+deb13u1_amd64.deb; \
    test -z "$(dpkg --audit)"
ARG RUN_USER
USER ${RUN_USER}
