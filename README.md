### ローカルで動かす場合

```bash
git clone https://github.com/rebi06/ddos-defense-lab.git
cd ddos-defense-lab
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn backend.app:app --reload
```

## 遊び方

1. ブラウザでダッシュボードを開く
2. 「Scenario start」を押す
3. ヒントを読んでトラフィックを分析する
4. IP Tracker を見て攻撃者を特定する
5. 適切な防御策を選んで実行する
6. 攻撃が収束したら自動でレポートが表示される

## スコアリング

| 条件 | 減点 |
|---|---|
| 誤検知（正常ユーザーをブロック） | -15点 × 件数 |
| 防御発動まで15秒超20秒以内 | -10点 |
| 防御発動まで20秒超25秒以内 | -20点 |
| 防御発動まで25秒超 | -30点 |
| ブロック率80%未満 | -20点 |
| 正常ユーザーへの影響 | -10点 × 件数 |
| 自動クリア達成 | +10点ボーナス |

## 攻撃シナリオと推奨対応

| シナリオ | 特徴 | 推奨対応 |
|---|---|---|
| Flood | 単一IPから大量アクセス | Rate limiting ON |
| Distributed | 複数IPから同時攻撃 | 手動ブロック → Rate limiting ON |
| Slowloris | 低速・高レイテンシ | 攻撃IPだけ手動ブロック |

## ディレクトリ構成
ddos-defense-lab/

├── backend/

│   ├── app.py       # FastAPI エンドポイント・WebSocket

│   ├── metrics.py   # リクエスト数・CPU・メモリ収集

│   ├── defense.py   # レート制限・IPブロック

│   ├── alerts.py    # アラート検知エンジン

│   ├── attacker.py  # 攻撃シミュレーター

│   └── scenario.py  # シナリオ管理・スコアリング

├── frontend/

│   └── index.html   # リアルタイムダッシュボード

├── attacker/

│   └── generator.py # 手動負荷テストツール

├── Dockerfile

├── docker-compose.yml

└── requirements.txt