# 触摸屏问题诊断指南

## 当前配置状态

### I2C时钟频率
- **项目源码DTB**: 1 MHz (1000000 Hz)
- **实际使用DTB**: 400 kHz (400000 Hz) ← `/boot/sc8280xp-huawei-gaokun3.dtb`
- **状态**: 有意配置为较低频率（可能有其原因）

### 设备信息
- **触摸屏设备**: `hid-over-i2c 4858:121A` (event11)
- **手写笔设备**: `hid-over-i2c 4858:121A Stylus` (event12)
- **I2C总线**: GENI SE4 at 0x990000
- **I2C地址**: 0x4F (HID event interface)

### 已知问题
启动时有2个I2C传输错误：
```
i2c_hid_of 4-004f: i2c_hid_get_input: incomplete report (44/40863)
```

---

## "不跟手"症状分类

### A. 延迟/滞后
**症状**: 触摸响应有明显延迟，手指移动后光标滞后跟随
**可能原因**:
- I2C采样频率不足
- 触摸固件处理延迟
- compositor处理延迟
- 系统负载过高

### B. 坐标不准
**症状**: 触摸点与实际位置有偏移
**可能原因**:
- 坐标校准问题
- 显示旋转与触摸映射不匹配
- 坐标转换矩阵错误

### C. 丢失/跳跃
**症状**: 触摸过程中光标突然跳到其他位置或消失
**可能原因**:
- I2C传输错误（如上面的incomplete report）
- 信号干扰
- 触摸固件bug

### D. 方向错误
**症状**: 触摸方向与手指移动方向不一致（如左右反向）
**可能原因**:
- 坐标转换矩阵配置错误
- 显示旋转与触摸旋转不匹配

---

## 诊断步骤

### 1. 实时监控触摸事件

```bash
# 安装evtest
sudo pacman -S evtest  # Arch
# 或
sudo apt install evtest  # Debian/Ubuntu

# 监控触摸事件
sudo evtest /dev/input/event11

# 观察：
# - 坐标是否随手指平滑变化
# - 是否有明显的跳跃或丢失
# - ABS_MT_POSITION_X/Y的范围 (应该是0-4095)
# - 时间戳是否连续
```

### 2. 检查I2C频率影响

```bash
# 查看当前I2C频率
fdtget /boot/sc8280xp-huawei-gaokun3.dtb /soc@0/geniqup@9c0000/i2c@990000 clock-frequency

# 备份当前DTB
sudo cp /boot/sc8280xp-huawei-gaokun3.dtb /boot/sc8280xp-huawei-gaokun3.dtb.backup

# 测试1MHz (如果当前是400kHz)
sudo fdtput -t i /boot/sc8280xp-huawei-gaokun3.dtb /soc@0/geniqup@9c0000/i2c@990000 clock-frequency 1000000
# 重启测试

# 如果问题加重，恢复400kHz
sudo cp /boot/sc8280xp-huawei-gaokun3.dtb.backup /boot/sc8280xp-huawei-gaokun3.dtb
```

### 3. 检查坐标映射

```bash
# 查看当前显示方向
xrandr --query | grep "connected"

# 检查libinput设备信息
libinput list-devices /dev/input/event11

# 查看坐标转换矩阵
xinput list-props "hid-over-i2c 4858:121A" | grep "Coordinate Transformation Matrix"

# 如果方向错误，可能需要调整矩阵
# 示例：旋转90度
xinput set-prop "hid-over-i2c 4858:121A" "Coordinate Transformation Matrix" 0 1 0 -1 0 1 0 0 1
```

### 4. 监控I2C错误

```bash
# 统计I2C错误数量
journalctl -b | grep "i2c_hid.*incomplete report" | wc -l

# 实时监控I2C错误
journalctl -f | grep -i "i2c_hid\|i2c.*4-004f"

# 查看完整的I2C通信日志
journalctl -b | grep "i2c.*4-004f" | less
```

### 5. 检查触摸恢复服务

```bash
# 查看服务状态
systemctl status hx83121a-touch-recovery.service

# 如果服务未运行，手动测试
sudo /usr/local/bin/hx83121a-touch-recovery

# 查看恢复日志
journalctl -u hx83121a-touch-recovery.service -b
```

### 6. 性能测试

```bash
# 检查系统负载
top -bn1 | head -15

# 检查compositor性能
# 如果使用GNOME/Mutter:
gnome-shell --version
journalctl -f | grep "mutter\|clutter"

# 测试触摸响应时间
# 使用evtest同时记录触摸和显示更新
```

---

## 历史背景

### 为什么I2C频率设置为400kHz？

根据项目提交历史和配置：
- 项目源码默认是1MHz
- `/boot`中的DTB被修改为400kHz
- 可能的原因（需要确认）：
  - 1MHz下I2C传输不稳定，导致更多错误
  - 400kHz更稳定，容错性更好
  - 电源管理考虑
  - 特定固件版本兼容性

### I2C频率vs稳定性

**400kHz的优点**:
- 更稳定的I2C通信
- 更低的传输错误率
- 更好的兼容性
- 更低的功耗

**1MHz的优点**:
- 更快的采样率（理论上）
- 更低的延迟（如果通信稳定）

**权衡**: 如果1MHz导致更多"incomplete report"错误，那么实际性能可能更差。400kHz虽然慢，但如果通信稳定，整体体验可能更好。

---

## 建议的排查顺序

1. **先确认症状类型** - 使用evtest诊断是延迟、坐标不准、还是跳跃
2. **检查I2C错误频率** - 如果错误很多，说明通信不稳定
3. **测试不同I2C频率** - 比较400kHz和1MHz的表现
4. **检查坐标映射** - 如果方向错误，调整转换矩阵
5. **检查系统负载** - 高负载可能导致延迟
6. **查看触摸固件日志** - 确认固件工作正常

---

## 关键问题

在修改任何配置之前，请回答：

1. "不跟手"具体是什么感觉？
   - [ ] 有明显延迟
   - [ ] 坐标不准
   - [ ] 经常跳跃/丢失
   - [ ] 方向错误

2. 问题是持续的还是在特定情况下出现？

3. 之前使用1MHz时是否有类似问题？

4. Windows下的触摸体验如何？（对比参考）

---

**创建日期**: 2026年4月10日
**相关文档**:
- `docs/TOUCHSCREEN.md` - 触摸屏技术文档
- `tools/touchscreen/hx83121a-touch-recovery` - 恢复脚本
- `README.md` - 项目说明（I2C速度优化章节）