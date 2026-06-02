#!/bin/bash
# ╔══════════════════════════════════════════════════════════╗
# ║  安幕诺家族 · 小红 🌹 Skills 插件安装器                   ║
# ║  对标 JoelLewis/finance_skills → install.sh              ║
# ╚══════════════════════════════════════════════════════════╝
#
# 特性:
#   - 符号链接安装（零拷贝，修改即生效）
#   - 依赖感知（自动先安装依赖插件）
#   - 去重机制（跳过已安装）
#
# 用法:
#   ./install.sh --plugin wealth-management --target ~/my-project
#   ./install.sh --plugin all --target ~/my-project
#   ./install.sh --list

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGINS_DIR="$SCRIPT_DIR/plugins"

# ═══════════════════════════════════════
# 依赖映射
# ═══════════════════════════════════════
declare -A PLUGIN_DEPS
PLUGIN_DEPS[core]=""
PLUGIN_DEPS[wealth-management]="core"
PLUGIN_DEPS[trading-operations]="core"
PLUGIN_DEPS[compliance]="core"
PLUGIN_DEPS[data-integration]="core"
PLUGIN_DEPS[advisory-practice]="core wealth-management"
PLUGIN_DEPS[client-operations]="core"

# ═══════════════════════════════════════
# 函数
# ═══════════════════════════════════════

installed_plugins=()

install_plugin() {
    local plugin=$1
    local target=$2

    # 去重
    for installed in "${installed_plugins[@]}"; do
        if [[ "$installed" == "$plugin" ]]; then
            return 0
        fi
    done

    # 递归安装依赖
    local deps="${PLUGIN_DEPS[$plugin]}"
    if [[ -n "$deps" ]]; then
        for dep in $deps; do
            install_plugin "$dep" "$target"
        done
    fi

    local plugin_dir="$PLUGINS_DIR/$plugin"
    if [[ ! -d "$plugin_dir" ]]; then
        echo "  ⚠️ 插件目录不存在: $plugin_dir (跳过)"
        return 1
    fi

    local skills_dir="$plugin_dir/skills"
    if [[ ! -d "$skills_dir" ]]; then
        echo "  ⚠️ 技能目录不存在: $skills_dir (跳过)"
        return 1
    fi

    local target_skills="$target/.claude/skills"
    mkdir -p "$target_skills"

    local count=0
    for skill_dir in "$skills_dir"/*/; do
        local skill_name=$(basename "$skill_dir")
        local link_path="$target_skills/$skill_name"

        if [[ -L "$link_path" ]]; then
            # 已存在，跳过
            continue
        fi

        ln -s "$(realpath "$skill_dir")" "$link_path"
        count=$((count + 1))
    done

    installed_plugins+=("$plugin")
    echo "  ✅ $plugin: $count 技能已安装 → $target_skills/"
}

list_plugins() {
    echo ""
    echo "📦 可用插件:"
    echo "──────────────────────────────────────────────"
    for plugin_dir in "$PLUGINS_DIR"/*/; do
        local name=$(basename "$plugin_dir")
        local deps="${PLUGIN_DEPS[$name]}"
        local skill_count=$(find "$plugin_dir/skills" -maxdepth 1 -type d 2>/dev/null | tail -n +2 | wc -l)
        
        if [[ -n "$deps" ]]; then
            echo "  $name ($skill_count 技能) → 依赖: $deps"
        else
            echo "  $name ($skill_count 技能)"
        fi
    done
    echo ""
}

# ═══════════════════════════════════════
# 主逻辑
# ═══════════════════════════════════════

PLUGIN=""
TARGET=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --plugin) PLUGIN="$2"; shift 2 ;;
        --target) TARGET="$2"; shift 2 ;;
        --list)   list_plugins; exit 0 ;;
        *) echo "未知参数: $1"; exit 1 ;;
    esac
done

if [[ "$PLUGIN" == "all" ]]; then
    echo "📦 安装全部插件..."
    for plugin in "${!PLUGIN_DEPS[@]}"; do
        install_plugin "$plugin" "${TARGET:-$HOME/.claude}"
    done
elif [[ -n "$PLUGIN" ]]; then
    echo "📦 安装插件: $PLUGIN"
    install_plugin "$PLUGIN" "${TARGET:-$HOME/.claude}"
else
    echo "用法: $0 --plugin <name|all> [--target <dir>]"
    echo "      $0 --list"
    exit 1
fi

echo ""
echo "✅ 安装完成: ${#installed_plugins[@]} 个插件"
for p in "${installed_plugins[@]}"; do
    echo "   $p"
done

# ═══════════════════════════════════════
# 克隆上游仓库（首次使用）
# ═══════════════════════════════════════
clone_upstream() {
    local upstream="https://github.com/JoelLewis/finance_skills.git"
    local target="$PLUGINS_DIR/../finance_skills_upstream"
    
    if [[ ! -d "$target" ]]; then
        echo "📥 克隆上游仓库: $upstream"
        git clone --depth 1 "$upstream" "$target"
        echo "✅ 上游仓库已克隆到: $target"
        echo "   可参考其中的技能实现"
    fi
}
