# GitHub SSH 配置与推送指南

## 前提条件

- GitHub 账号已登录
- 已生成或准备好 SSH key

## 步骤 1: 检查现有 SSH keys

```bash
ls -al ~/.ssh
```

查看是否已有密钥文件（如 `id_rsa.pub`, `id_ed25519.pub` 等）

## 步骤 2: 生成新的 SSH key（如果没有）

```bash
# 推荐：Ed25519（更安全、更快）
ssh-keygen -t ed25519 -C "your_email@example.com"

# 或使用 RSA（兼容性更好）
ssh-keygen -t rsa -b 4096 -C "your_email@example.com"
```

按提示操作：
- 文件位置：默认 `~/.ssh/id_ed25519`（或直接回车）
- 密码短语：可以留空或设置密码

## 步骤 3: 启动 SSH agent 并添加密钥

```bash
# 启动 SSH agent
eval "$(ssh-agent -s)"

# 添加私钥到 agent
ssh-add ~/.ssh/id_ed25519
# 或
ssh-add ~/.ssh/id_rsa
```

## 步骤 4: 复制公钥内容

```bash
cat ~/.ssh/id_ed25519.pub
# 或
cat ~/.ssh/id_rsa.pub
```

复制输出的完整公钥（以 `ssh-ed25519` 或 `ssh-rsa` 开头）

## 步骤 5: 添加公钥到 GitHub

1. 登录 GitHub.com
2. 点击右上角头像 → Settings
3. 左侧菜单选择 "SSH and GPG keys"
4. 点击 "New SSH key"
5. 填写：
   - Title: 例如 "MateBook E Go Linux"
   - Key: 粘贴步骤4复制的公钥
6. 点击 "Add SSH key"

## 步骤 6: 测试 SSH 连接

```bash
ssh -T git@github.com
```

成功输出示例：
```
Hi username! You've successfully authenticated, but GitHub does not provide shell access.
```

## 步骤 7: 配置 Git 使用 SSH（如果当前使用 HTTPS）

```bash
cd /home/whitelewis/Documents/matebook-e-go-linux

# 查看当前 remote URL
git remote -v

# 如果是 HTTPS，切换为 SSH
git remote set-url origin git@github.com:YOUR_USERNAME/matebook-e-go-linux.git

# 验证更改
git remote -v
```

## 步骤 8: 提交并推送本次更新

### 检查当前状态

```bash
git status
git log --oneline -5
```

### 查看本次新增的文件

```bash
git diff --stat
```

本次更新应该包含：
- `tools/update-firmware.sh` - 自动化更新脚本
- `device-tree/sc8280xp-huawei-gaokun3-calibration-standalone.dtso` - 独立DTBO源文件
- `device-tree/sc8280xp-huawei-gaokun3-calibration-standalone.dtbo` - 编译后的DTBO
- `FIRMWARE_UPDATE_REPORT.md` - 更新报告
- `tools/waydroid/90-waydroid-network-fix` - 修复后的网络脚本

### 提交更改

```bash
# 添加所有更改
git add tools/update-firmware.sh
git add device-tree/sc8280xp-huawei-gaokun3-calibration-standalone.dtso
git add device-tree/sc8280xp-huawei-gaokun3-calibration-standalone.dtbo
git add FIRMWARE_UPDATE_REPORT.md
git add tools/waydroid/90-waydroid-network-fix

# 或者一次性添加所有更改
git add -A

# 查看将要提交的内容
git status
```

### 创建提交

```bash
git commit -m "tools: add firmware update automation and improve waydroid network fix

- Add update-firmware.sh: automated script for WiFi DTBO and Waydroid setup
- Create standalone WiFi calibration DTBO (no kernel source dependency)
- Fix waydroid-network-fix: correct container route syntax and add polling
- Add FIRMWARE_UPDATE_REPORT.md: comprehensive update documentation

Tested on kernel 6.18.8-gaokun3, WiFi calibration verified working,
Waydroid network fix installed successfully.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

### 推送到 GitHub

```bash
# 推送到 master 分支
git push origin master

# 如果是首次推送，可能需要设置 upstream
git push -u origin master
```

## 步骤 9: 验证推送成功

```bash
# 检查远程状态
git remote show origin

# 查看远程分支
git branch -r

# 查看最近的提交是否已推送
git log origin/master --oneline -5
```

访问 GitHub 仓库页面确认更新已上传。

---

## 可选：配置 SSH key 自动加载

创建或编辑 `~/.bashrc` 或 `~/.zshrc`：

```bash
# 自动启动 SSH agent
if [ -z "$SSH_AUTH_SOCK" ]; then
   eval "$(ssh-agent -s)"
   ssh-add ~/.ssh/id_ed25519 2>/dev/null
fi
```

或创建 `~/.ssh/config`：

```
Host github.com
    HostName github.com
    User git
    IdentityFile ~/.ssh/id_ed25519
    AddKeysToAgent yes
```

---

## 故障排查

### SSH 连接失败

```bash
# 详细调试模式
ssh -Tv git@github.com

# 检查密钥权限
chmod 700 ~/.ssh
chmod 600 ~/.ssh/id_ed25519
chmod 644 ~/.ssh/id_ed25519.pub
```

### 推送被拒绝

```bash
# 检查是否有未合并的远程更改
git fetch origin
git log HEAD..origin/master

# 如果有冲突，先合并
git pull --rebase origin master
git push origin master
```

---

## 快速命令参考

完整的推送流程（从项目根目录）：

```bash
cd /home/whitelewis/Documents/matebook-e-go-linux
git add tools/update-firmware.sh \
        device-tree/sc8280xp-huawei-gaokun3-calibration-standalone.dtso \
        device-tree/sc8280xp-huawei-gaokun3-calibration-standalone.dtbo \
        FIRMWARE_UPDATE_REPORT.md \
        tools/waydroid/90-waydroid-network-fix
git status
git commit -m "tools: add firmware update automation and improve waydroid network fix"
git push origin master
```

---

**创建日期**: 2026年4月10日
**适用环境**: Huawei MateBook E Go Linux 项目