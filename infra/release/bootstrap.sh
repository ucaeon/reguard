#!/usr/bin/env bash
set -euo pipefail
# Run as root on a dedicated ARM64 Linux server. Application installation is separate.
[[ $(id -u) == 0 && $(uname -s) == Linux && $(uname -m) == aarch64 ]] || { echo 'Requires root on ARM64 Linux' >&2; exit 1; }
version='v1.35.5+k3s1'
if command -v k3s >/dev/null; then
  [[ $(k3s --version | head -1) == "k3s version ${version} "* ]] || { echo 'Existing k3s version differs' >&2; exit 1; }
  command -v ctr >/dev/null || ln -s /usr/local/bin/k3s /usr/local/bin/ctr
  echo 'Pinned k3s already installed'; exit 0
fi
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
base="https://github.com/k3s-io/k3s/releases/download/$version"
curl --fail --location --retry 3 "$base/k3s-arm64" -o "$work/k3s-arm64"
curl --fail --location --retry 3 "$base/sha256sum-arm64.txt" -o "$work/checksums"
(cd "$work"; awk '$2 == "k3s-arm64" {print}' checksums | sha256sum -c -)
install -m 0755 "$work/k3s-arm64" /usr/local/bin/k3s
install -d -m 0700 /etc/rancher/k3s
cat > /etc/rancher/k3s/config.yaml <<'EOF'
write-kubeconfig-mode: '0600'
secrets-encryption: true
disable: [traefik, servicelb]
kubelet-arg:
  - 'system-reserved=cpu=200m,memory=300Mi'
  - 'kube-reserved=cpu=200m,memory=512Mi'
  - 'eviction-hard=memory.available<200Mi,nodefs.available<10%'
EOF
cat > /etc/systemd/system/k3s.service <<'EOF'
[Unit]
Description=ReGuard k3s
After=network-online.target
Wants=network-online.target
[Service]
Type=notify
ExecStart=/usr/local/bin/k3s server
Restart=always
RestartSec=5
KillMode=process
Delegate=yes
LimitNOFILE=1048576
LimitNPROC=infinity
LimitCORE=infinity
TasksMax=infinity
TimeoutStartSec=0
[Install]
WantedBy=multi-user.target
EOF
command -v kubectl >/dev/null || ln -s /usr/local/bin/k3s /usr/local/bin/kubectl
command -v ctr >/dev/null || ln -s /usr/local/bin/k3s /usr/local/bin/ctr
systemctl daemon-reload
systemctl enable --now k3s
# The server needs outbound access for k3s system images; application images come from the bundle.
k3s kubectl wait --for=condition=Ready node --all --timeout=300s
