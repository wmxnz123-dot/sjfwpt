# 原型标注检查清单

## 当前标注统计

- 页面数量：50
- 标注数量：214
- 标注模式：standard
- 标注类型统计：A:33、AI:1、C:113、DATA:1、FALLBACK:1、J:9、P:50、S:6
- 缺少页面级说明标注的页面：未提供
- 仅页面介绍的页面：未提供
- 未转正候选：0
- 粗粒度锚点：0
- review.required 绕过：0
- 二级界面数量：81
- 覆盖不完整的二级界面：surface-P03-confirmmodal、surface-P03-alertmodal、surface-P06-draweroverlay、surface-P06-resourcedetaildrawer、surface-P06-confirmmodal、surface-P06-renewmodal、surface-P06-alertmodal、surface-P07-draweroverlay、surface-P07-resourcedetaildrawer、surface-P07-confirmmodal、surface-P07-alertmodal、surface-P08-draweroverlay、surface-P08-cappackdrawer、surface-P09-smart-catalog-drawer、surface-P09-smart-fill-modal、surface-P10-audit-drawer、surface-P10-smart-audit-drawer、surface-P12-filter-linked、surface-P12-filter-status、surface-P13-scenedraweroverlay、surface-P13-scenedetaildrawer、surface-P14-edit-api-modal、surface-P14-upload-attachment-modal、surface-P15-draweroverlay、surface-P15-dataresourcedrawer、surface-P15-confirmmodal、surface-P15-alertmodal、surface-P16-auditdraweroverlay、surface-P16-auditdrawer、surface-P16-passmodaloverlay、surface-P16-confirmmodal、surface-P16-alertmodal、surface-P17-draweroverlay、surface-P17-dataresourcedrawer、surface-P18-auditdraweroverlay、surface-P18-auditdrawer、surface-P18-confirmmodal、surface-P18-alertmodal、surface-P19-accept-drawer、surface-P19-smart-audit-drawer、surface-P20-draweroverlay、surface-P20-detaildrawer、surface-P25-accept-drawer、surface-P25-smart-audit-drawer、surface-P29-demand-modal、surface-P30-demand-modal、surface-P30-api-add-basket-modal、surface-P30-basket-success-modal、surface-P36-quotaauditdrawer、surface-P36-assignmodal、surface-P36-quotaviewdrawer、surface-P36-rejectmodal、surface-P37-databasketdrawer、surface-P37-submitapplymodal、surface-P38-databasketdrawer、surface-P38-fieldmodaloverlay、surface-P38-submitapplymodal、surface-P38-confirmmodal、surface-P38-alertmodal、surface-P39-databasketdrawer、surface-P39-submitapplymodal、surface-P39-apiaddtobasketmodaloverlay、surface-P39-alertmodal、surface-P41-createscenemodal、surface-P41-confirmmodal、surface-P41-alertmodal、surface-P42-filter-interface-source、surface-P43-global-smart-drawer、surface-P43-quick-fill-modal、surface-P45-global-smart-drawer、surface-P45-quick-fill-modal、surface-P48-ai-drawer-overlay、surface-P48-ai-drawer、surface-P48-resourcedetailmodal、surface-P49-draweroverlay、surface-P49-appliedresourcedrawer、surface-P49-ownresourcedrawer、surface-P49-addappliedresourcemodal、surface-P49-addappliedresourcedrawer、surface-P49-addownresourcemodal、surface-P49-addownresourcedrawer

## 1. 页面覆盖检查

- [x] 每个页面都有页面级说明标注
- [ ] 每个页面至少有一个关键操作标注
- [x] 每个页面的主路径跳转已标注
- [ ] 每个二级界面至少有入口与概览标注

## 2. 交互检查

- [x] 主按钮已标注操作结果
- [x] 异步操作已标注 loading / 成功 / 失败反馈
- [x] 失败状态已标注
- [x] 空状态已标注

## 3. 状态与规则检查

- [x] 关键状态已标注
- [ ] 关键规则已标注
- [x] 权限相关操作已标注
- [x] 业务规则异常分支已标注

## 4. 产品形态扩展检查

- [x] AI 产品已标注 AI 输入 / 输出 / 人工确认 / 失败兜底
- [x] 数据产品已标注指标口径 / 数据来源 / 刷新频率
- [ ] SaaS 产品已标注角色权限 / 套餐权益 / 租户隔离
- [ ] C端产品已标注关键转化节点 / 埋点事件
- [x] B端产品已标注流程 / 权限 / 状态 / 业务规则

## 5. 研发交付缺口

- [x] 所有需转正的候选点均已落入 annotations.json
- [x] 非页面介绍标注未使用 main/h1/body 级粗锚点
- [x] AI 标注均保留 review.required=true

## 6. 待确认项

- [ ] 标注内容是否准确
- [ ] 标注是否过多
- [ ] 标注是否覆盖关键交互
- [ ] 是否存在未解释的按钮
- [ ] 是否存在未说明的状态
