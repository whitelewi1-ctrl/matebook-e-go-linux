# 触摸屏"不跟手"渲染问题诊断

## 发现的关键问题

### 1. DRM/DPU VBlank超时错误
从内核日志发现：
```
[dpu error]vblank timeout: 400000
[dpu error]wait for commit done returned -110
```

这表明：
- DPU（Display Processing Unit）等待帧提交超时
- 可能导致帧丢失或渲染延迟
- 直接影响触摸响应的流畅度

### 2. 当前渲染配置

**显示管线**:
- 驱动: `msm_dpu` (Qualcomm DPU)
- 连接器: DSI-1
- 模式: 1600x2560
- DPMS: On
- Format: XR30 (30-bit RGB)
- Modifier: 0x500000000000001 (可能与压缩/tiling相关)

**GNOME/Mutter**:
- Compositor: GNOME Shell (Wayland)
- 实验性功能: `scale-monitor-framebuffer`
- GPU: Adreno 690 (FD690)
- 直接渲染: 已启用

**内核参数**:
- `clk_ignore_unused` - 忽略未使用的时钟
- `pd_ignore_unused` - 忽略未使用的电源域
- 无 `fbcon=rotate` 参数（显示旋转由GNOME处理）

---

## "不跟手"的可能原因

### A. DPU帧提交延迟
**症状**: 触摸事件处理正常，但视觉反馈滞后
**原因**: vblank timeout导致帧丢失
**影响**: 轻微到中度的延迟感

### B. GPU渲染负载
**症状**: 系统负载高时触摸响应变差
**原因**: GPU忙于渲染其他任务
**影响**: 间歇性延迟

### C. Wayland/Native旋转开销
**症状**: 横屏使用时延迟明显
**原因**: 软件旋转（1600x2560→2560x1600）消耗资源
**影响**: 持续性延迟

### D. 触摸采样率不足
**症状**: 快速滑动时跳跃
**原因**: I2C 400kHz采样率
**影响**: 快速操作时不流畅
**已排除**: 1MHz会导致显示问题

---

## 诊断步骤

### 1. 监控帧率和帧时间

```bash
# 安装gnome-shell扩展或使用工具
# 监控帧率
export DISPLAY=:0
gnome-shell --version

# 查看Mutter性能统计
gsettings set org.gnome.mutter debug-mode true
journalctl -f | grep -i "mutter\|clutter"

# 实时监控GPU负载
watch -n 1 "cat /sys/class/drm/card1/device/gpu_busy 2>/dev/null || echo 'No gpu_busy'"
```

### 2. 测试原生vs旋转性能

```bash
# 测试竖屏模式（原生，无旋转）
gsettings set org.gnome.mutter experimental-features "[]"
# 注销重新登录

# 测试横屏模式（软件旋转）
gsettings set org.gnome.mutter experimental-features "['scale-monitor-framebuffer']"
# 注销重新登录

# 比较触摸响应
```

### 3. 监控DPU错误频率

```bash
# 统计vblank timeout错误
dmesg | grep "vblank timeout" | wc -l

# 实时监控DPU错误
watch -n 1 "dmesg | tail -20 | grep -i 'dpu\|vblank\|drm'"

# 触摸时监控
dmesg -w | grep -E "dpu|dsi|vblank" &
# 然后滑动屏幕
```

### 4. 测试不同刷新率

```bash
# 查看可用刷新率
cat /sys/class/drm/card1-DSI-1/modes

# 如果支持60Hz和120Hz，测试差异
xrandr --output DSI-1 --mode 1600x2560 --rate 60
# vs
xrandr --output DSI-1 --mode 1600x2560 --rate 120
```

### 5. 禁用不必要的GNOME效果

```bash
# 禁用动画
gsettings set org.gnome.desktop.interface enable-animations false

# 禁用搜索索引
gsettings set org.gnome.desktop.search-providers disable-external true

# 检查是否有性能改善
```

---

## 可能的解决方案

### 方案1: 优化DPU性能

创建 `/etc/tmpfiles.d/dpu-performance.conf`:

```bash
# 提高GPU频率（需要root）
w /sys/class/kgsl/kgsl-3d0/devfreq/governor - - - - performance
w /sys/class/kgsl/kgsl-3d0/max_pwrlevel - - - - 0
```

应用：
```bash
sudo systemd-tmpfiles --create
```

### 方案2: 内核参数优化

在 `/etc/default/grub` 中添加：

```bash
GRUB_CMDLINE_LINUX_DEFAULT="... msm_dpu.dpu_dbg_bus=0"
```

或调整电源管理：
```bash
GRUB_CMDLINE_LINUX_DEFAULT="... pcie_aspm=off"
```

### 方案3: 使用fbcon旋转替代软件旋转

测试是否内核级旋转更高效：

```bash
# 编辑GRUB
sudo nano /etc/default/grub

# 添加
GRUB_CMDLINE_LINUX_DEFAULT="... fbcon=rotate:1 video=DSI-1:1600x2560@60,rotate=1"

# 更新GRUB
sudo update-grub
# 或
sudo grub-mkconfig -o /boot/grub/grub.cfg

# 注销并测试
```

注意：这会改变整个显示栈的旋转方式，可能影响其他应用。

### 方案4: 降低渲染负载

```bash
# 禁用或降低GNOME Shell效果
gsettings set org.gnome.desktop.interface enable-animations false
gsettings set org.gnome.shell.extensions.user-theme name 'Adwaita'

# 检查扩展
gnome-extensions list --enabled
# 禁用不必要的扩展
```

---

## 对比测试建议

创建测试矩阵：

| 配置 | 触摸响应 | 帧率 | vblank错误 | 备注 |
|------|----------|------|------------|------|
| 当前（软件旋转） | ? | ? | ? | 基线 |
| 竖屏（无旋转） | ? | ? | ? | 对照组 |
| fbcon旋转 | ? | ? | ? | 内核级 |
| 禁用动画 | ? | ? | ? | 轻量化 |

每个配置测试：
1. 快速滑动流畅度
2. 慢速绘制精度
3. 多点触控响应
4. 系统负载影响

---

## 关键问题

1. vblank timeout是否频繁发生？（统计次数）
2. 竖屏模式下是否也有"不跟手"？
3. 120Hz vs 60Hz是否有差异？
4. 禁用动画后是否改善？

---

**创建日期**: 2026年4月10日
**相关日志**: vblank timeout, DPU commit timeout
**下一步**: 等待用户反馈具体的延迟症状