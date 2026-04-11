# 触摸屏优化配置指南

## 问题诊断

### 1. I2C速度偏低
**当前**: 400 kHz (默认)
**推荐**: 1 MHz (可减少触摸延迟)

### 2. 触摸恢复服务未启用
触摸恢复服务 `hx83121a-touch-recovery.service` 当前已禁用。

### 3. 可能的坐标映射问题
触摸坐标系可能需要与显示器旋转匹配。

---

## 优化步骤

### 步骤 1: 提高I2C时钟频率到1MHz

这可以减少触摸采样延迟，改善响应速度：

```bash
# 备份当前DTB
sudo cp /boot/sc8280xp-huawei-gaokun3.dtb /boot/sc8280xp-huawei-gaokun3.dtb.backup

# 修改I2C时钟频率
cd /home/whitelewis/Documents/matebook-e-go-linux
sudo fdtput -t i device-tree/sc8280xp-huawei-gaokun3.dtb /soc@0/geniqup@9c0000/i2c@990000 clock-frequency 1000000

# 验证修改
fdtget device-tree/sc8280xp-huawei-gaokun3.dtb /soc@0/geniqup@9c0000/i2c@990000 clock-frequency

# 复制到boot
sudo cp device-tree/sc8280xp-huawei-gaokun3.dtb /boot/

# 重启后生效
```

### 步骤 2: 启用触摸恢复服务

```bash
sudo systemctl enable hx83121a-touch-recovery.service
sudo systemctl start hx83121a-touch-recovery.service
```

### 步骤 3: 检查libinput配置（可选）

如果提高I2C速度后仍有问题，可以调整libinput设置：

创建 `/etc/X11/xorg.conf.d/99-touchscreen.conf` (X11):

```xorg
Section "InputClass"
        Identifier "Touchscreen"
        MatchIsTouchscreen "on"
        MatchDevicePath "/dev/input/event*"
        Option "TransformationMatrix" "0 1 0 -1 0 1 0 0 1"
        Option "CalibrationMatrix" "0 1 0 -1 0 1 0 0 1"
        Driver "libinput"
        Option "Tapping" "on"
        Option "TappingDrag" "on"
EndSection
```

注意：如果触摸坐标反向，调整TransformationMatrix为：
- 顺时针90度: `0 1 0 -1 0 1 0 0 1`
- 逆时针90度: `0 -1 1 1 0 0 0 0 1`
- 180度: `-1 0 1 0 -1 1 0 0 1`

对于Wayland (GNOME/Mutter)，使用：
```bash
# 列出设备
libinput list-devices

# 查找触摸屏设备
xinput list

# 应用转换矩阵（设备ID可能不同）
xinput set-prop "hid-over-i2c 4858:121A" "Coordinate Transformation Matrix" 0 1 0 -1 0 1 0 0 1
```

### 步骤 4: 验证优化效果

重启后检查：

```bash
# 验证I2C速度
cat /sys/bus/i2c/devices/4-004f/of_node/clock-frequency 2>/dev/null || echo "Property not set"

# 从DTB验证
fdtget device-tree/sc8280xp-huawei-gaokun3.dtb /soc@0/geniqup@9c0000/i2c@990000 clock-frequency

# 检查触摸恢复服务
systemctl status hx83121a-touch-recovery.service

# 测试触摸响应
evtest /dev/input/event11
```

---

## 快速测试命令

测试当前触摸坐标输出：

```bash
sudo evtest /dev/input/event11
```

触摸屏幕，观察：
- 坐标是否跟随手指移动
- 坐标范围是否匹配屏幕分辨率 (1600x2560)
- 是否有明显的延迟或跳跃

---

## 预期改善

- ✅ I2C速度提升：减少触摸采样延迟
- ✅ 触摸恢复服务：确保触摸固件正确初始化
- ✅ 坐标映射：修正触摸方向与显示匹配

---

## 故障排查

### 触摸完全无响应

```bash
# 检查I2C设备
ls /sys/bus/i2c/devices/4-004f/

# 重新加载HID驱动
sudo rmmod hid_multitouch
sudo modprobe hid_multitouch

# 手动触发触摸恢复
sudo /usr/local/bin/hx83121a-touch-recovery
```

### 触摸坐标反向或旋转

调整坐标转换矩阵，参见步骤3。

### I2C速度修改后设备无法识别

恢复备份：
```bash
sudo cp /boot/sc8280xp-huawei-gaokun3.dtb.backup /boot/sc8280xp-huawei-gaokun3.dtb
```

---

**创建日期**: 2026年4月10日
**适用设备**: Huawei MateBook E Go (Himax HX83121A TDDI)