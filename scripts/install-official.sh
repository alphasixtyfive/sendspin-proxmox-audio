#!/bin/sh
set -eu

# Run only inside the newly approved CT, after native bootstrap creates its audio user.
test "$#" -eq 1 || { echo 'usage: install-official.sh EXPECTED_CT_HOSTNAME' >&2; exit 2; }
test "$(id -u)" -eq 0
test "$(hostname)" = "$1"
test "$(systemd-detect-virt --container)" = lxc
test "$(dpkg --print-architecture)" = amd64
. /etc/os-release
test "$ID" = debian
test "$VERSION_ID" = 13
test "$(getent passwd sendspin-cli | cut -d: -f6)" = /var/lib/sendspin-cli
test -d /var/lib/sendspin-cli
if systemctl is-active --quiet sendspin-cli.service; then
    echo 'The single-player system service is active; refuse duplicate ownership.' >&2
    exit 1
fi
for task_comm in /proc/[0-9]*/comm; do
    test -r "$task_comm" || continue
    IFS= read -r task_name < "$task_comm" || continue
    if test "$task_name" = sendspin-cli; then
        echo 'Stop all CT player processes before installing the release.' >&2
        exit 1
    fi
done

task_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
archive=sendspin-cli-0.4.0-linux-x86_64.tar.gz
expected=40efcab39ef303d026d8880ad1ada7b53b29e806114ae3744f9ed33daee0c5d9
cache=/var/cache/sendspin-cli/v0.4.0
apt-get update
apt-get install -y --no-install-recommends ca-certificates curl libasound2t64 libportaudio2 libpulse0 libpipewire-0.3-0 libavahi-compat-libdnssd1
install -d -m 0755 "$cache"
if test -f "$task_dir/$archive"; then
    install -m 0644 "$task_dir/$archive" "$cache/$archive"
else
    curl --fail --location --proto '=https' --tlsv1.2 \
        "https://github.com/Sendspin/sendspin-cpp-cli/releases/download/v0.4.0/$archive" \
        --output "$cache/$archive"
fi
printf '%s  %s\n' "$expected" "$cache/$archive" | sha256sum --check --status
tar -xzf "$cache/$archive" --strip-components=1 -C / sendspin-cli-0.4.0-linux-x86_64/usr
tar -xOf "$cache/$archive" sendspin-cli-0.4.0-linux-x86_64/BUILD-INFO.txt > "$cache/BUILD-INFO.txt"
printf '%s  %s\n' 350b891ed3f11b73cf428cb7dc8bc8a9dd809892515c69fb2bca6724867cda7b /usr/local/bin/sendspin-cli | sha256sum --check
systemd-sysusers /usr/local/lib/sysusers.d/sendspin-cli.conf
systemctl daemon-reload
/usr/local/bin/sendspin-cli --version
# Deliberately do not enable/start the shipped single-player system unit.
