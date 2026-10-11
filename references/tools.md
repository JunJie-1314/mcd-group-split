# 麦当劳中国 MCP 工具速查

> 服务端点 `https://mcp.mcd.cn`，传输 Streamable HTTP，鉴权头 `Authorization: Bearer <token>`。
> 限流：每 Token 每分钟 600 次（超限 `429`）。
> 服务器实时返回的 input schema 优先于本文档；参数有出入以运行时为准。

## 一、本技能实际使用的工具

拼单闭环只用到下面这些，按模式归类。

### 模式 1 · 发起拼单

| Tool | 作用 | 关键注意 |
|---|---|---|
| `now-time-info` | 返回当前完整时间信息 | 判断早餐/正餐/夜宵档位，避免推荐已停售品类 |
| `query-nearby-stores` | 查询指定地址附近的餐厅 | 到店自取 / 堂食场景 |
| `delivery-query-stores` | 查询收货地址附近可配送门店 | 外送场景，需先有地址 |
| `delivery-query-addresses` | 查询用户已创建的配送地址 | 外送时用来选地址 |
| `query-meal-assistance` | 查询门店助餐服务 | **仅企业团餐场景** |
| `query-meals` | 查询门店当前可售餐品列表 | 分类、餐品编码、标签；**金额是「元」字符串** |
| `query-meal-detail` | 按餐品编码查询详情与套餐组成 | 看套餐包含什么、可替换项 |

### 模式 2 · 券后最优

| Tool | 作用 | 关键注意 |
|---|---|---|
| `available-coupons` | 查询当前**可领取**的麦麦省券 | 只查不领 |
| `auto-bind-coupons` | **一键领取**所有当前可用券 | ⚠️ 写操作，领券前须说明 |
| `query-my-coupons` | 查「我的」可用券列表 | 汇总券池用 |
| `query-store-coupons` | 查当前门店下可用券 | 门店专属券常被忽略，别漏 |
| `campaign-calendar` | 查询当月营销活动日历 | 返回进行中 / 往期 / 未来活动 |
| `calculate-price` | 按商品列表计算金额、配送费、优惠、应付 | ⚠️ **返回的价格字段单位是「分」** |

### 模式 4 · 下单

| Tool | 作用 | 关键注意 |
|---|---|---|
| `create-order` | 创建订单，返回订单详情与支付链接 | ⚠️ 写操作，须用户明确确认 |
| `query-order` | 查询订单状态与内容 | 下单后核对 |
| `cancel-order` | 取消订单 | ⚠️ 写操作 |
| `order-list` | 查询近期到店/外送历史订单 | 不含商城订单 |

## 二、其余工具（本技能未用，列全便于扩展）

| 分类 | Tools |
|---|---|
| 营养 | `list-nutrition-foods`（能量/蛋白/脂肪/碳水/钠/钙，可做指定热量搭配） |
| 地址 | `delivery-create-address`（⚠️ 写操作，会向麦当劳提交姓名/手机号/地址） |
| 积分账户 | `query-my-account`（可用/累计/冻结/即将过期积分） |
| 麦麦商城 | `mall-points-products`、`mall-product-detail`、`mall-create-order`（⚠️ 写操作）、`mall-order-list`、`mall-order-detail` |
| 积分抽奖 | `query-lottery-info`、`draw-lottery`（⚠️ 消耗积分）、`query-my-prizes` |
| 主题活动 | `query-party-city`、`query-party-store`、`query-party-store-date`、`query-party-store-session`、`party-order-create`（⚠️ 写操作） |
| 营销与问卷 | `query-promotions`（当前营销活动/优惠）、`query-survey-coupon`（问卷类券） |

## 三、三个必须记住的坑

### 1. 价格单位不统一（最高频翻车点）

- **仅** `calculate-price` 返回的价格字段是**「分」**（无引号整数）→ 展示前除以 100。
- `query-meals`、`query-meal-detail`、`create-order`、`query-order`、麦麦商城订单返回的是**「元」字符串** → 直接用。
- 所有积分字段（`points`、`totalPoints` 等）**不做金额换算**。

不要「一概除以 100」，也不要「一概不除」，按工具区分。

### 2. 写操作必须用户确认

`auto-bind-coupons`、`create-order`、`cancel-order`、`delivery-create-address`、
`mall-create-order`、`draw-lottery`、`party-order-create` 都会改变账户状态或消耗权益。
浏览、咨询阶段**不要触发**；只有用户明确点头后才调用。

### 3. 错误码

| 码 | 原因 | 处理 |
|---|---|---|
| `401` | Token 无效、过期或未提供 | 引导用户去 `open.mcd.cn/mcp` 重新获取并更新配置 |
| `429` | 超过 600 次/分钟 | 降低频率、合并请求、稍后重试 |

## 四、安全与隐私

- 任何情况下都不在回答、日志、命令参数或文件中暴露 `MCP Token` 明文。
- 展示手机号时脱敏为 `152****6666`。
- 新增地址会把姓名、手机号、详细地址发给麦当劳，只收集任务必需的数据。
- 支付由用户在返回链接或麦当劳 App 内自行完成，Agent 不代付。
