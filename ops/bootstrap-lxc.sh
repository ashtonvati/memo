#!/usr/bin/env bash
set -euo pipefail

# Run once as root inside the dedicated LXC after adding the GitHub deploy key.
readonly REPO_URL="git@github.com:ashtonvati/memo.git"
readonly REPO_DIR="/opt/moment"

apt-get update
apt-get install -y ca-certificates curl git gnupg openssh-client
install -m 0755 -d /etc/apt/keyrings
source /etc/os-release
if [ "${ID}" != "debian" ] && [ "${ID}" != "ubuntu" ]
then
    echo "Unsupported LXC distribution: ${ID}" >&2
    exit 1
fi
curl -fsSL "https://download.docker.com/linux/${ID}/gpg" \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/${ID} ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

id -u moment >/dev/null 2>&1 || useradd --create-home --shell /bin/bash moment
usermod -aG docker moment
install -d -o moment -g moment -m 0700 /home/moment/.ssh
install -d -m 0750 /etc/moment

if [ ! -d "${REPO_DIR}/.git" ]
then
    runuser -u moment -- git clone "${REPO_URL}" "${REPO_DIR}"
fi

install -o moment -g moment -m 0755 "${REPO_DIR}/ops/moment-deploy.sh" /usr/local/sbin/moment-deploy
install -m 0644 "${REPO_DIR}/ops/moment-deploy.service" /etc/systemd/system/moment-deploy.service
install -m 0644 "${REPO_DIR}/ops/moment-deploy.timer" /etc/systemd/system/moment-deploy.timer
systemctl daemon-reload

echo "Create /etc/moment/backend.env, then run:"
echo "  systemctl enable --now moment-deploy.timer"
echo "  systemctl start moment-deploy.service"
