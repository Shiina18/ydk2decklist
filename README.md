# YGOPRO ydk to decklist PDF

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://ydk2decklist.streamlit.app)
[![feedback badge](https://img.shields.io/badge/feedback-点我反馈-blue?logo=coveralls)](https://www.wjx.cn/vm/Q0KmBoa.aspx)
![last commit badge](https://img.shields.io/github/last-commit/shiina18/ydk2decklist?label=更新时间)
[![Update database](https://github.com/Shiina18/ydk2decklist/actions/workflows/update-database.yml/badge.svg)](https://github.com/Shiina18/ydk2decklist/actions/workflows/update-database.yml)

拖拽上传 YDK 文件, 生成多语种 **可编辑** PDF 卡表

- 支持卡名语种: 日文, 简中, 英文
- 支持 PDF 模板 (布局): [简中](https://db.yugioh-card-cn.com/%E6%B8%B8%E6%88%8F%E7%8E%8B%E7%89%8C%E8%A1%A8-%E7%AE%80%E4%B8%AD.pdf), [英文](https://img.yugioh-card.com/en/downloads/forms/KDE_DeckList.pdf)

## 说明

- 各语种卡表卡名位置一致
- 无简中译名的中文卡名前有 "(旧译)" 标识以示区分
- 写不下的怪兽 (中文模板 20 行, 英文模板 18) 输出在本网页, 需手动编辑; 但卡表上显示的怪兽总数依然计入没写在表上的卡

**模板:** PDF 布局

- 中文模板常常显示不全卡名, 且没有提示
- 英文模板 Foxit 可能有卡名显示不全, 有加号提示, 打印时要注意
  - 目前仅发现一例《スターダスト・チャージ・ウォリアー》, 浏览器上可正常显示

**输出 PDF**

- Adobe Reader 无法正常显示输出的 PDF, 可用 [Foxit](https://www.foxit.com/pdf-reader/) 或者 Chrome 浏览器打开
- 输出的 PDF 每个栏目底下 TOTAL XXX 统计数值写死了, 不会自动更新, 事后手动修改 PDF 时要注意

**链接**

- [卡表填写注意事项](https://mp.weixin.qq.com/s/lpKTkOnqrGFfsjROtoJUKA) @chosKD
- [简中官方数据库](https://db.yugioh-card-cn.com/)
- [百鸽游戏王卡查](https://ygocdb.com/)

## Changelog

- 每日上午自动更新本地卡片数据库 (2023-03-05)
- 修复部分卡名关联错误问题, 感谢 "蛋" 反馈 (2023-02-01 14:40)
  - 影响范围: 此前, "这张卡的卡名在规则上当作「xx」使用" 这类卡卡名关联错误, 比如《融合》会错误写为《置换融合》
- 新增功能: 写不下的怪兽自动填到魔法栏底部 (2023-01-21 10:21)
- 修复无法关联《閃刀姫－アザレア》(id 100200228) 的问题 (2023-01-20 16:29)
- 修复无法关联部分异画卡的问题 (2023-01-20 15:21)
