# MateBook E Go 固件更新报告

**日期**: 2026年4月10日
**内核版本**: 6.18.8-gaokun3

## 更新内容概述

根据项目最近的提交（2383c1e 到 d3270c4），本次更新包含以下内容：

### 1. WiFi校准DTBO Overlay ✅ 已完成

**状态**: 已经正确配置，无需额外操作

**检测结果**:
- ✅ 设备树中已包含 `qcom,ath11k-calibration-variant = "HW_GK3"`
- ✅ WiFi正在正常工作（已连接到网络 "BROWN"）
- ✅ 使用正确的qmi-chip-id=18（HW_GK3）校准数据

**路径**: `/sys/firmware/devicetree/base/soc@0/pcie@1c00000/pcie@0/wifi@0/qcom,ath11k-calibration-variant`

**验证方法**:
```bash
cat /sys/firmware/devicetree/base/soc@0/pcie@1c00000/pcie@0/wifi@0/qcom,ath11k-calibration-variant
iw dev wlan0 info
```

---

### 2. Waydroid网络修复 ✅ 已安装

**状态**: NetworkManager dispatcher脚本已成功安装

**已完成的操作**:
- ✅ 安装了新的NetworkManager dispatcher脚本 `/etc/NetworkManager/dispatcher.d/90-waydroid-network-fix`
- ✅ 禁用并停止了旧的systemd服务 `waydroid-net-fix.service`
- ✅ 重新加载了NetworkManager配置

**改进点**:
- 从硬编码的15秒sleep改为智能轮询（最多30秒）
- 通过NetworkManager事件自动触发（接口up/down）
- 在容器内添加默认路由：`waydroid shell -- ip route add default via 192.168.240.1`
- 防止路由冲突和重复添加

**测试注意**:
由于DBus session bus限制，`waydroid session start`在纯终端环境下可能失败。
建议在图形界面环境（Wayland/GNOME）下启动Waydroid以完整测试网络功能。

**验证方法**（在Wayland环境下）:
```bash
waydroid show-full-ui
waydroid shell -- ip route show
```

---

### 3. 内核配置检查 ⚠️ 需要关注

**状态**: IP转发运行时已启用，但内核编译时未明确设置

**检测结果**:
- ✅ `CONFIG_NF_TABLES=y` - nftables支持
- ✅ `CONFIG_NF_TABLES_INET=y` - IPv4/IPv6 nftables
- ✅ `CONFIG_NFT_NAT=y` - NAT支持
- ✅ `CONFIG_NFT_MASQ=y` - MASQUERADE支持
- ✅ `CONFIG_NFT_CT=y` - 连接跟踪
- ⚠️ `CONFIG_IP_FORWARD` - 运行时已启用（值为1），但内核配置中未明确设置

**当前运行状态**:
```bash
$ cat /proc/sys/net/ipv4/ip_forward
1
$ sysctl net.ipv4.ip_forward
net.ipv4.ip_forward = 1
```

**建议**:
虽然IP转发在运行时已启用，但建议在下次重新编译内核时明确设置：
```bash
scripts/config --enable CONFIG_IP_FORWARD
```

这确保Waydroid容器NAT功能更稳定，不依赖于运行时配置。

---

## 备用方案

### WiFi校准（如果主DTB不包含）

如果主DTB不包含校准配置（本次检测显示已包含，无需此步骤），可以使用独立DTBO：

```bash
cd /home/whitelewis/Documents/matebook-e-go-linux/device-tree
dtc -@ -@ -o sc8280xp-huawei-gaokun3-calibration-standalone.dtbo \
    sc8280xp-huawei-gaokun3-calibration-standalone.dtso
sudo cp sc8280xp-huawei-gaokun3-calibration-standalone.dtbo /lib/firmware/ath11k/
```

### Waydroid Play Protect认证

如果需要Google Play认证：
```bash
mkdir -p /var/lib/waydroid/overlay/system
cp /var/lib/waydroid/rootfs/system/build.prop /var/lib/waydroid/overlay/system/build.prop
sed -i 's/test-keys/release-keys/g; s/userdebug/user/g' /var/lib/waydroid/overlay/system/build.prop
```

然后访问 https://www.google.com/android/uncertified/ 注册设备ID。

---

## 下一步建议

1. **测试Waydroid网络**：在GNOME/Wayland环境下启动Waydroid验证网络功能
2. **内核重建**：下次重建内核时添加 `CONFIG_IP_FORWARD=y`
3. **完整文档**：参考 `docs/WIFI_CALIBRATION_DTBO.md` 和 `docs/BUILDING.md`

---

## 文件变更清单

**已安装文件**:
- `/etc/NetworkManager/dispatcher.d/90-waydroid-network-fix` (新)

**已修改状态**:
- `waydroid-net-fix.service` (已禁用)

**已创建文件（备用）**:
- `/home/whitelewis/Documents/matebook-e-go-linux/device-tree/sc8280xp-huawei-gaokun3-calibration-standalone.dtbo`
- `/home/whitelewis/Documents/matebook-e-go-linux/tools/update-firmware.sh` (自动化脚本)

---

**报告生成**: Claude Code
**版权**: GPL-2.0-or-later