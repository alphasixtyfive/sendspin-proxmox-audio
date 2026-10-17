#!/bin/sh
set -eu

# Run inside the dedicated CT after creating its audio account.
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
test "$(id -u sendspin-cli)" -gt 0
id -nG sendspin-cli | tr ' ' '\n' | grep -Fxq audio

if systemctl is-active --quiet sendspin-cli.service; then
    echo 'The single-player system service is active; stop and disable it first.' >&2
    exit 1
fi
system_unit_state=$(systemctl is-enabled sendspin-cli.service 2>/dev/null || true)
case "$system_unit_state" in
    enabled|enabled-runtime)
        echo 'Disable the single-player system service before installing this multiroom setup.' >&2
        exit 1
        ;;
esac
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

stage=$(mktemp -d "$cache/install.XXXXXX")
binary_stage=
cleanup() {
    test -z "$binary_stage" || rm -f -- "$binary_stage"
    rm -rf -- "$stage"
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
tar -xOf "$cache/$archive" sendspin-cli-0.4.0-linux-x86_64/usr/local/bin/sendspin-cli > "$stage/sendspin-cli"
tar -xOf "$cache/$archive" sendspin-cli-0.4.0-linux-x86_64/BUILD-INFO.txt > "$stage/BUILD-INFO.txt"
printf '%s  %s\n' 350b891ed3f11b73cf428cb7dc8bc8a9dd809892515c69fb2bca6724867cda7b "$stage/sendspin-cli" | sha256sum --check

# The seven user services replace the upstream single-player system service.
systemctl mask sendspin-cli.service
binary_stage=$(mktemp /usr/local/bin/.sendspin-cli.XXXXXX)
install -m 0755 "$stage/sendspin-cli" "$binary_stage"
mv -f -- "$binary_stage" /usr/local/bin/sendspin-cli
binary_stage=
install -m 0644 "$stage/BUILD-INFO.txt" "$cache/BUILD-INFO.txt"
systemctl daemon-reload
/usr/local/bin/sendspin-cli --version
