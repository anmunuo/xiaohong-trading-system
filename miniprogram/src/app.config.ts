{
  "pages": [
    "pages/dashboard/index",
    "pages/signals/index",
    "pages/positions/index",
    "pages/stats/index",
    "pages/settings/index"
  ],
  "window": {
    "navigationBarTitleText": "安幕诺家族 · 小红",
    "navigationBarBackgroundColor": "#0f172a",
    "navigationBarTextStyle": "white",
    "backgroundColor": "#0a0e1a"
  },
  "tabBar": {
    "color": "#64748b",
    "selectedColor": "#f43f5e",
    "backgroundColor": "#111827",
    "borderStyle": "black",
    "list": [
      {
        "pagePath": "pages/dashboard/index",
        "text": "仪表盘",
        "iconPath": "assets/tab/dashboard.png",
        "selectedIconPath": "assets/tab/dashboard-active.png"
      },
      {
        "pagePath": "pages/signals/index",
        "text": "信号",
        "iconPath": "assets/tab/signals.png",
        "selectedIconPath": "assets/tab/signals-active.png"
      },
      {
        "pagePath": "pages/positions/index",
        "text": "持仓",
        "iconPath": "assets/tab/positions.png",
        "selectedIconPath": "assets/tab/positions-active.png"
      },
      {
        "pagePath": "pages/stats/index",
        "text": "统计",
        "iconPath": "assets/tab/stats.png",
        "selectedIconPath": "assets/tab/stats-active.png"
      },
      {
        "pagePath": "pages/settings/index",
        "text": "设置",
        "iconPath": "assets/tab/settings.png",
        "selectedIconPath": "assets/tab/settings-active.png"
      }
    ]
  },
  "permission": {
    "scope.userLocation": { "desc": "用于展示本地市场时间" }
  },
  "requiredPrivateInfos": [],
  "usingComponents": {}
}
