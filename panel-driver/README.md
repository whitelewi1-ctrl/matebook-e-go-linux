This directory no longer carries the local out-of-tree DSI panel implementation.

The repository now assumes:

- upstream SC8280XP DSI controller/PHY support
- upstream `panel-himax-hx83121a`

Keep board-specific DTS changes in `device-tree/` and remaining local kernel fixes in `kernel-patches/`.
