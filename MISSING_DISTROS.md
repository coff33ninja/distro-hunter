# Missing Distros And Builds

This is the queue of official images that are still worth adding after the current built-in set.

## Harder Sources

- MX Linux
  - Official page: https://mxlinux.org/download-links/
  - Notes: multiple mirrors and flavor pages need a cleaner selection rule.

## Good Next Wave

- Additional Fedora ARM and alternate-architecture desktops
  - Official page: https://fedoraproject.org/spins/
  - Notes: a small ARM64 Fedora set is built in now, but there are still more alternate architectures and editions if you want them.
- Additional Garuda variants or kernels if the release thread format changes
  - Official page: https://forum.garudalinux.org/c/announcements/iso-releases/
  - Notes: the current built-ins cover the main flavors from the latest ISO release thread.

## Source Problems To Revisit

- Kali stable live, live-everything, installer-everything, and weekly live images
  - Official page: https://www.kali.org/get-kali/
  - Notes: the page advertises these builds, but the direct image URLs were returning `404 Not Found` on March 30, 2026.

## Installed Images Not Covered By distro_hunter

Snapshot note (2026-10-14): these are currently usable under Bootimus even though they do not have a matching built-in/system-update path in distro_hunter.

- Untracked installed Linux images:
  - `omarchy-4.0.0.iso` (`linux/omarchy/...`)
  - `winux-11.26.08-noble-lts.iso` (flat `linux/` root)
- Built-in plugins with no imported image:
  - `rocky_boot`, `rocky_dvd`, `rocky_minimal`
  - `zorin_core`, `zorin_education`, `zorin_lite`
  - `fydeos_pc_amd`, `fydeos_pc_modern`, `fydeos_pc_slim`
  - `steamos_recovery`
  - `systemrescue`
  - `ubuntu_budgie_lts`
  - `ubuntu_studio_lts`
  - `ubuntu_cinnamon_lts` (may be represented as `ubuntucinnamon`, but no dedicated family mapping)
- Manual/duplicate placements recorded under Bootimus:
  - `linux/manual/*` (Alpine, Arch Linux, Fedora Budgie) are duplicates for plugin-backed distros
  - `linux/kali-linux-2026.1-installer-netinst-amd64.iso` is duplicated as a root extra
- Unmanaged temp snapshots retained as reminders:
  - `TrueNAS-SCALE-24.10.0.2.iso`
  - `openKylin-1.0-x86_64.iso`
  - `wanulator_2_2_02.iso`
