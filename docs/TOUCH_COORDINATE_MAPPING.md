# 触摸坐标映射问题诊断

## 问题分析

根据evtest输出，触摸硬件工作正常：
- 坐标平滑连续（无跳跃）
- 采样率正常（~10ms）
- 坐标范围正确（0-4096）

**"不跟手"的根本原因：触摸坐标映射与竖屏显示不匹配**

### 当前配置
- **显示分辨率**: 1600x2560（竖屏）
- **触摸坐标范围**: 0-4096 (X和Y)
- **显示旋转**: 未在内核参数中设置 `fbcon=rotate:1`
- **GNOME缩放**: 未启用

### 坐标映射问题

竖屏显示（1600x2560）需要触摸坐标旋转映射：
- 触摸X坐标 → 显示Y坐标
- 触摸Y坐标 → 显示X坐标
- 可能需要镜像或反向

---

## 解决方案

### 方案1：内核参数旋转（推荐）

在GRUB中添加 `fbcon=rotate:1` 参数：

```bash
# 编辑GRUB配置
sudo nano /etc/default/grub

# 在GRUB_CMDLINE_LINUX_DEFAULT中添加：
GRUB_CMDLINE_LINUX_DEFAULT="... fbcon=rotate:1"

# 更新GRUB
sudo update-grub  # Debian/Ubuntu
# 或
sudo grub-mkconfig -o /boot/grub/grub.cfg  # Arch

# 重启
```

这会告诉内核framebuffer和输入子系统屏幕是竖屏，自动处理旋转。

### 方案2：libinput quirks（Wayland）

创建 `/etc/libinput/local-overrides.quirks`:

```ini
[Touchscreen Rotation]
MatchName=hid-over-i2c 4858:121A
AttrEventCode=-ABS_X;+ABS_Y;-ABS_Y;+ABS_X
AttrEventCode=-ABS_MT_POSITION_X;+ABS_MT_POSITION_Y;-ABS_MT_POSITION_Y;+ABS_MT_POSITION_X
```

这告诉libinput交换X/Y坐标。

### 方案3：udev规则

创建 `/etc/udev/rules.d/99-touchscreen-rotation.rules`:

```bash
# 旋转触摸屏90度
ACTION=="add|change", KERNEL=="event*", SUBSYSTEM=="input", ATTRS{name}=="hid-over-i2c 4858:121A", ENV{LIBINPUT_CALIBRATION_MATRIX}="0 1 0 -1 0 1"

# 或180度
# ENV{LIBINPUT_CALIBRATION_MATRIX}="-1 0 1 0 -1 1"

# 或270度
# ENV{LIBINPUT_CALIBRATION_MATRIX}="0 -1 1 1 0 0"
```

然后重新加载udev：
```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

### 方案4：xinput映射（仅X11/XWayland）

如果使用X11应用：
```bash
# 列出设备
xinput list

# 设置转换矩阵（旋转90度）
xinput set-prop "hid-over-i2c 4858:121A" "Coordinate Transformation Matrix" 0 1 0 -1 0 1 0 0 1
```

要永久化，创建 `~/.config/autostart/touchscreen-rotate.desktop`:

```ini
[Desktop Entry]
Type=Application
Name=Touchscreen Rotation
Exec=sh -c 'xinput set-prop "hid-over-i2c 4858:121A" "Coordinate Transformation Matrix" 0 1 0 -1 0 1 0 0 1'
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
```

---

## 测试方法

### 1. 验证坐标方向

```bash
# 运行evtest
sudo evtest /dev/input/event11

# 水平滑动手指（左→右）
# 观察：ABS_X应该增加
# 如果ABS_Y增加，说明X/Y交换了

# 垂直滑动手指（上→下）
# 观察：ABS_Y应该增加
# 如果ABS_X增加，说明X/Y交换了
```

### 2. 测试映射方案

测试不同的转换矩阵，找到正确的旋转：

```bash
# 0度（无旋转）
xinput set-prop "hid-over-i2c 4858:121A" "Coordinate Transformation Matrix" 1 0 0 0 1 0 0 0 1

# 90度顺时针
xinput set-prop "hid-over-i2c 4858:121A" "Coordinate Transformation Matrix" 0 1 0 -1 0 1 0 0 1

# 180度
xinput set-prop "hid-over-i2c 4858:121A" "Coordinate Transformation Matrix" -1 0 1 0 -1 1 0 0 1

# 270度顺时针（90度逆时针）
xinput set-prop "hid-over-i2c 4858:121A" "Coordinate Transformation Matrix" 0 -1 1 1 0 0 0 0 1
```

逐个测试，找到触摸方向正确的矩阵。

---

## 推荐操作流程

1. **先测试内核参数** `fbcon=rotate:1` - 最简单直接
2. **如果无效**，使用udev规则（方案3）- 持久化且适用于Wayland
3. **精确测试**，使用xinput临时调整，找到正确矩阵后写入配置

---

## 为什么I2C频率不是问题

项目历史表明：
- 1MHz会导致**显示无法正常工作**
- 400kHz虽然理论采样率较低，但**实际体验取决于坐标映射和compositor处理**
- 当前evtest显示触摸事件正常，问题在于坐标映射

---

**创建日期**: 2026年4月10日
**适用设备**: Huawei MateBook E Go (竖屏1600x2560)