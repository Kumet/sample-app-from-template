# サンプルアプリ開発結果レポート

## 1. 結論

Local Project Boardのサンプルアプリ開発は、main commit
`27f372ac967a8c684a0294e645a6b81faf611195`で一区切りとした。

完成したものは、個人または小規模チームがローカル環境で利用できる
Project Boardである。REST APIとブラウザUIの両方から、Project、Task、
Tag、Commentを操作できる。データはSQLiteへ保存され、Project dashboard、
Task検索、Comment activity履歴、Docker Composeによる再現可能なローカル
起動にも対応している。

同時に、このリポジトリはAI開発テンプレートの実アプリ審査環境として
機能した。仕様作成から実装、検証、独立review、PR、CI、high-risk承認まで
を繰り返し、実際に見つかったframework上の問題をテンプレート側で修正し、
sampleへ同期する運用を検証した。

## 2. アプリ概要

### 利用者と用途

- ローカルでProjectとTaskを管理したい個人開発者
- 小規模な開発・作業チーム
- REST APIとWeb UIの双方を使って同じデータを操作したい利用者
- 仕様駆動AI開発プロセスの検証対象を必要とする開発者

### 実装済み機能

| 領域 | 実装内容 |
|---|---|
| Project | 作成、一覧、詳細、更新、削除 |
| Task | Project配下でのCRUD、status、priority、description、期限 |
| Task query | キーワード、複数status、複数priority、Tag、期限、sort、pagination |
| Tag | Project-scoped CRUD、Taskへのattach/detach |
| Comment | Task配下でのCRUD、validation、pagination |
| Activity | Comment作成・更新・削除のappend-only履歴 |
| Dashboard | Task、status、priority、期限、Tag、Comment、recent activity集計 |
| Web UI | Project Boardの主要操作を行うHTML/CSS/vanilla JavaScript UI |
| Health | database非依存の`GET /health` |
| Container | multi-stage image、非root実行、Compose、SQLite volume永続化 |
| CI | 通常validationと独立したcontainer build/smoke job |

### 意図的に未実装のもの

- CLI
- JSON import / export
- SQLite backup / restore
- production database migration framework
- authentication / authorization
- real-time collaboration
- production deployment
- mobile application

これらは欠陥ではなく、現在の承認済みscope外である。追加する場合は新しい
Feature仕様が必要となる。

## 3. アーキテクチャ

アプリケーションは次の責務分離を維持している。

```text
Browser UI / FastAPI routes
            |
            v
Application services
            |
            v
Repository interfaces
            |
            v
SQLAlchemy repositories -> SQLite

Domain entities / value rules are independent from SQLAlchemy.
```

主な構成は以下のとおり。

- `src/project_board/domain/`
  - Project、Task、Tag、Comment、Activity、Dashboardの型と規則
- `src/project_board/application/`
  - use case、Project存在確認、transaction orchestration
- `src/project_board/repositories/`
  - stack-independent interfaceとSQLAlchemy実装
- `src/project_board/infrastructure/`
  - SQLAlchemy model、database/session初期化
- `src/project_board/api/`
  - FastAPI route、request/response schema、Web asset route
- `src/project_board/web/`
  - packageへ同梱されるHTML、CSS、vanilla JavaScript

application serviceやrepository interfaceをimportしただけではSQLAlchemy
具象実装をeager loadしない。API route内でSQL queryやtransactionを直接
組み立てず、既存serviceとrepositoryを経由する。

## 4. データと安全性

### SQLite

- Project、Task、Tag、Task–Tag association、Comment、Activityを永続化
- SQLite foreign key enforcementを有効化
- cross-project associationをserviceとdatabaseの両方で防止
- Comment mutationとActivity記録を同一transactionで処理
- development/testではSQLAlchemy metadata initializationを使用

正式なproduction migration frameworkは導入していない。既存databaseの
versioned upgradeが必要な運用へ進む場合は、別Featureとして設計する必要が
ある。

### Web UI security

- API由来文字列はsafe DOM APIと`textContent`で表示
- `innerHTML`、`eval`、inline script/style、外部CDNを不使用
- CSP、`nosniff`、frame protection、referrer policyを設定
- static assetsはpackage-relativeな固定pathだけを配信
- Project、Task、Tag、Commentなどのuser contentをHTMLとして解釈しない

### Container security

- `python:3.11.11-slim-bookworm`を使用
- builder/runtimeのmulti-stage build
- wheelだけをruntime imageへinstall
- UID/GID `10001:10001`の非root実行
- working directoryと永続書込み先を`/data`へ限定
- Composeは`127.0.0.1`へだけport publish
- capability drop、`no-new-privileges`、`init: true`
- `.dockerignore`でGit、tests、specs、agent evidence、secret候補、SQLiteを除外

## 5. どのように作ったか

各アプリFeatureは次の流れで作成した。

1. 人間がFeatureの目的、scope、禁止事項、停止条件を承認
2. `spec.md`でrequirementsとacceptance criteriaを固定
3. clarificationで既存契約との矛盾を解消
4. `plan.md`でarchitecture、transaction、test方針を決定
5. `tasks.md`へ最大10個の実装taskとして分解
6. version 2 `validation.toml`でrisk、scope、command、traceabilityを固定
7. isolated Git worktree上でtask単位に実装・検証・commit
8. tracked validation snapshotをcommit
9. 同一exact HEADでfull validationとweakening検査を実行
10. spec-scope、security、tests、maintainability、integrationの独立review
11. risk gate通過後にbranch push、ready-for-review PR、GitHub Actions
12. 人間承認後にmainへmergeし、framework cleanupを実行

重要な判断は推測せず、仕様矛盾、scope追加、review budget exhaustion、
high-risk pre-pushなどで停止して人間承認を求めた。

## 6. 実装Feature

### アプリFeature

| Feature | 内容 |
|---|---|
| 001 | Project CRUD |
| 002 | Task CRUD |
| 003 | Project-scoped Task Tags |
| 004 | Task query |
| 005 | Task Comments and Activity History |
| 018 | Project Dashboard Analytics |
| 019 | Project Board Web UI |
| 020 | Containerized Operational Readiness |

Feature番号006〜017はframework仕様との衝突を避けるため、6番目のアプリ
Featureから018以降を使用した。

### Sampleへ反映した主なframework Feature

| Feature | 審査・改善内容 |
|---|---|
| 005 | scope request normalization |
| 007 | review resumeとexact SHA attribution |
| 008 | state-aware delivery dry-run |
| 009 | ownership markerをcleanとして扱う検証 |
| 010 | bounded review call policy |
| 011 | empty review shard inputのfail-closed処理 |
| 012 | review evidence semantics |
| 013 | review budget exhaustion後の安全なresume |
| 014 | approved recovery patch re-attribution |
| 015 | weakening evidence semantics |
| 016 | repair後のvalidation→weakening→review順序 |
| 017 | non-required findingとgate verdictの分離 |
| 021 | container validation Make target policy |
| 022 | skip検出のtoken boundary修正 |
| 023 | canonical redacted review evidence |

## 7. テンプレート審査結果

### 総合評価

テンプレートは、長期間・複数Featureにまたがる実アプリ開発を、scopeと
evidenceを維持しながら完了できた。特に次の仕組みが実運用で機能した。

- approved specをsource of truthとして実装を制限
- allowed/forbidden pathによるscope enforcement
- isolated worktreeとownership marker
- state-aware dry-runとresume safety
- validation contractのREQ→AC→Task traceability
- exact HEADへ帰属するvalidation/review evidence
- append-only runtime events
- weakening detectionとtest削除・skip・CI無効化のfail-closed検査
- required findingとnon-required findingの分離
- bounded review budgetとbudget exhaustion時の9回目起動防止
- high-risk pre-push approval gate
- secret-shaped情報をredactしたcanonical review payload

### 実アプリ審査で見つかった問題

初期状態のframeworkだけで全Featureを無停止に完了できたわけではない。
実アプリdeliveryにより、以下のような共通問題が再現され、テンプレート側で
修正された。

- review結果やaggregateのexact identity不足
- review call budgetを使い切った後のresume方法
- repair後にweakening evidenceを作る順序
- raw reviewer FAILと機械的gate PASSの意味論
- non-required findingをblockingとして扱う誤判定
- `SystemExit`内の`xit`をskip markerとみなすtoken境界誤検出
- Markdown説明用skip表記と実行可能skip callの区別
- redaction後payloadとdigestの不一致
- stopped worktreeへ人間承認repairを安全に帰属させる方法
- container専用validation targetとpolicy allowlistの不一致

問題をsample固有の回避コードで隠さず、テンプレートFeatureとして修正し、
template mainでvalidation・review・CIを通した後にsampleへ選択同期した。
この運用により、sampleとtemplateの責務分離を保つことができた。

### 最終審査結果

- mainへ統合されたPR: #1〜#24
- mainへの直接push: なし
- auto-merge: 不使用
- 最終app Feature exact validated HEAD:
  `4da49965ab28eae6c4cdd39beee12756fbda602a`
- 最終main merge commit:
  `27f372ac967a8c684a0294e645a6b81faf611195`
- framework tests: 127件PASS
- application tests: 601件PASS
- integration tests: 283件PASS
- Ruff、format、mypy、secret check、package build: PASS
- container build: PASS
- real container smoke: PASS
- GitHub Actions `validate`: PASS
- GitHub Actions `container`: PASS
- 最終independent review:
  spec-scope、security、tests、maintainability、integrationすべてPASS
- 最終required finding: なし
- Feature 020 runtime events: sequence 1〜90を監査証跡として保持

## 8. Container smokeで確認したこと

Feature 020のreal-container smokeは、mockだけでなくDocker daemon上の
実containerを使って次を確認した。

- image build成功
- runtime userが非root
- container healthがhealthy
- `GET /health`が200と`{"status":"ok"}`
- `/`、CSS、JavaScript assetを取得可能
- Projectの作成・取得
- containerを作り直しても同じvolume上のProjectが保持される
- logsにtracebackやsecret-shaped情報がない
- repository直下のSQLite fileを作成・変更しない
- test自身が作成したcontainer、network、volumeだけをcleanup

実ブラウザによる最終acceptanceは、Codexのbrowser runtimeが利用できなかった
ため未実施と記録した。HTTP、asset、DOM安全性、accessibility contract、
responsive contractは自動テスト済みだが、実ブラウザ確認をPASSとは偽装して
いない。

## 9. 現在の利用方法

### ローカル開発実行

```bash
python3.11 -m venv .venv
source .venv/bin/activate
make setup
python3 -m uvicorn project_board.main:app --reload
```

ブラウザで <http://127.0.0.1:8000/> を開く。

### Docker Compose

```bash
docker compose up --build
```

ブラウザで <http://127.0.0.1:8000/> を開く。停止時はdataを残す場合:

```bash
docker compose down
```

dataも削除する場合のみ、内容を確認して次を実行する。

```bash
docker compose down --volumes
```

## 10. 次に開発する場合の候補

優先候補は次のとおり。

1. JSON export / atomic import
2. SQLite backup / restore
3. CLI adapter
4. production migration方針
5. 実ブラウザによるdesktop/mobile acceptanceの完遂

新規開発を再開する場合も、現在と同じspecification-driven workflowを使用し、
既存Project/Task/Tag/Comment/Activity/Dashboard/Web/Container契約を回帰対象に
含めることを推奨する。

## 11. 監査証跡

- Feature仕様: `specs/<feature>/`
- tracked validation結果: 各Featureの`validation-log.md`
- runtime evidence: `.agent-work/<feature>/events.jsonl`
- framework運用説明: `docs/ai-operation.md`
- architecture: `docs/architecture.md`
- project context: `docs/project-context.md`

runtime evidenceはGit管理対象外だが、開発終了時点では削除せず保持している。
