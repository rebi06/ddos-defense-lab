# DDoS Defense Lab

Blue Team視点でDDoS攻撃の検知・防御・復旧を学べる教育用演習環境です。

## 概要

攻撃を受けながらリアルタイムで防御判断を行い、結果をスコアで評価します。
「攻撃者のIPを特定してブロックする」「正常ユーザーを巻き込まない」という
Blue Teamの本質的な判断力を鍛えることを目的としています。

## 機能

- リアルタイム監視（Requests/sec・Latency・CPU・Memory）
- WebSocketによる1秒ごとのダッシュボード更新
- 攻撃検知アラート（Traffic spike・High latency・Attack detected）
- 防御コントロール（Rate limiting・IP blocking・Emergency mode）
- 攻撃シナリオ3種（Flood・Distributed・Slowloris）
- 正常ユーザーの混在による誤検知体験
- 手動IPブロック
- ミッション自動クリア判定
- スコアリング・事後分析レポート

## 技術スタック

- Python 3.14
- FastAPI
- WebSocket
- uvicorn
- psutil
- Docker / Docker Compose

## セットアップ

### Docker を使う場合（推奨）

```bash
git clone https://github.com/rebi06/ddos-defense-lab.git
cd ddos-defense-lab
docker compose up --build
```

ブラウザで以下にアクセス