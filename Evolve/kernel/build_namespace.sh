#!/bin/bash
# Trusted launcher. Called inside fresh user, mount, PID and network namespaces.
set -euo pipefail
root=$1; source_tree=$2; output=$3; action=$4
mount --make-rprivate /
mount -t tmpfs -o size=128m tmpfs "$root"
mkdir -p "$root"/{usr/lib,usr/share,src,build,proc,tmp,dev}
for d in bin sbin; do ln -s "usr/$d" "$root/$d"; done
ln -s usr/lib "$root/lib"
mkdir -p "$root/lib64"
ln -s /usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2 "$root/lib64/ld-linux-x86-64.so.2"
for d in /etc/alternatives /usr/bin /usr/sbin /usr/include /usr/lib/x86_64-linux-gnu /usr/lib/gcc /usr/libexec /usr/lib/bfd-plugins /usr/lib/locale /usr/lib/python3.12 /usr/share; do
  [ -d "$d" ] || continue
  mkdir -p "$root$d"
  mount --bind "$d" "$root$d"
  mount -o remount,bind,ro "$root$d"
done
mount --bind "$source_tree" "$root/src"
mount -o remount,bind,ro "$root/src"
mount --bind "$output" "$root/build"
mount -t proc proc "$root/proc"
mount -t tmpfs -o size=64m,nosuid,nodev tmpfs "$root/tmp"
for d in null zero random urandom; do
  touch "$root/dev/$d"; mount --bind "/dev/$d" "$root/dev/$d"
done
# No host home, network, git metadata, sockets or credentials are mounted.
exec chroot "$root" /usr/bin/env -i PATH=/usr/bin:/bin HOME=/tmp LC_ALL=C \
 /usr/bin/setpriv --bounding-set=-all --inh-caps=-all --ambient-caps=-all --no-new-privs \
 /usr/bin/prlimit --as=2147483648 --fsize=536870912 --nofile=512 --nproc=512 \
 /bin/bash -euc '
   test ! -e /home
   test "$(ls /sys/class/net 2>/dev/null | wc -l)" = 0
   if [ "$1" = probe ]; then
      test ! -w /src/Makefile
      echo NAMESPACE_PROBE_PASS
      exit
   fi
   make -C /src O=/build olddefconfig
   make -C /src O=/build -j4 bzImage
 ' build "$action"
