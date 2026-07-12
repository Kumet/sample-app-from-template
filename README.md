# ai-dev-template

仕様・計画・タスク・検証条件を用意すると、Codexがタスクを1件ずつ実装し、
検証に合格するまで上限付きで修正を繰り返す開発テンプレートです。

Python、Web、AI、CLI、モバイルなど、技術スタックには依存しません。
プロジェクト固有の検証はMakeターゲットで接続します。

## 自動化されること

```text
承認済み仕様
  → 未完了タスクを1件選択
  → Codexで実装
  → テスト・変更範囲・secret検査
  → 失敗時は上限付きで修正
  → 成功時だけタスク完了化・ローカルコミット
  → 次のタスク
  → 全タスク完了後にmake validate
```

push、merge、デプロイ、仕様変更は自動実行しません。main/master、dirtyな
worktree、禁止ファイル変更、同一エラーの繰り返しでは安全に停止します。

## 必要なもの

- Git
- Make
- Python 3.11以上
- [Codex CLI](https://developers.openai.com/codex/cli/)
- Codex CLIの認証済み環境

## 新しいプロジェクトでの導入

GitHubの「Use this template」でリポジトリを作成し、cloneします。

```bash
git clone git@github.com:<owner>/<project>.git
cd <project>
./scripts/init-project.sh
```

次のファイルをプロジェクトに合わせて編集します。

1. `docs/project-context.md`: 目的、利用者、技術スタック、禁止事項
2. `docs/glossary.md`: AIが推測してはいけない用語
3. `Makefile`: lint、typecheck、test、buildなどの実コマンド
4. `README.md`: プロジェクト固有の案内

最低限、次のコマンドが実際の品質ゲートになるようにしてください。

```bash
make test
make validate
```

## 1. feature仕様を配置する

仕様は別工程で作成・承認し、featureごとに次の形式で配置します。

```text
specs/012-user-login/
  spec.md
  plan.md
  tasks.md
  validation.toml
  validation-log.md
```

ひな形は `specs/_template/` にあります。

### tasks.md

タスクID、関連要件、検証名を固定形式で書きます。

```markdown
- [ ] T001: ユーザーモデルを実装する
  - Requirements: REQ-001
  - Validation: unit
- [ ] T002: ログインAPIを実装する
  - Requirements: REQ-002
  - Validation: unit, full
```

`Validation` にはコマンドを書かず、`validation.toml` に登録した名前だけを
指定します。タスク本文がシェルとして実行されることはありません。

### validation.toml

実行可能な検証、リトライ上限、変更可能範囲を定義します。

```toml
version = 2
risk = "medium"
auto_merge = false
max_tasks = 20
max_attempts_per_task = 3
max_final_validation_attempts = 3
max_review_attempts = 3
max_ci_attempts = 3

[validations]
unit = "test"
full = "validate"

[traceability]
REQ-001 = ["AC-001", "T001"]
REQ-002 = ["AC-002", "T002"]

[dependencies]
T002 = ["T001"]

[scope]
allowed = [
  "src/**",
  "tests/**",
  "docs/**",
  "specs/012-user-login/**",
]
forbidden = [
  ".env",
  ".env.*",
  "**/.env",
  "**/.env.*",
  "local.properties",
  "**/*.pem",
  "**/*.key",
]
```

検証値は `.agent-policy.toml` で許可されたMakeターゲットだけを指定します。
任意の実行ファイルやシェル構文は実行できません。`traceability` は要件、
Acceptance Criteria、タスクを機械的に結び付けます。

## 2. featureブランチを準備する

仕様一式をレビューしてコミットした後、クリーンなfeatureブランチで実行します。

```bash
git switch -c feature/012-user-login
git add specs/012-user-login
git commit -m "spec: define user login"
```

main/masterまたは未コミット変更がある状態では `make work` は開始しません。

## 3. 実行内容を事前確認する

```bash
make validate-spec FEATURE=012-user-login
make spec-lint FEATURE=012-user-login
make work-dry-run FEATURE=012-user-login
```

dry-runでは次の情報だけを表示し、Codexの起動やファイル変更は行いません。

- featureと現在のブランチ
- 完了・未完了タスク
- 次に実行するタスク
- 実行予定の検証コマンド

## 4. 自動実装する

```bash
make work FEATURE=012-user-login
```

Codexは `workspace-write`、承認ポリシー `never` で非対話実行されます。
一度に実装するのは1タスクだけです。

各タスクでは以下を確認します。

- Codexの終了コード
- taskに指定された検証
- `git diff --check`
- secretファイル名
- 禁止ファイル
- allowed範囲外の変更

すべて成功した場合だけチェックボックスとvalidation logを更新し、ローカル
コミットを作成します。自動pushは行いません。

## 5. 状態とログを確認する

```bash
make work-status FEATURE=012-user-login
```

実行証跡はGit管理外の次の場所に保存されます。

```text
.agent-work/<feature>/<timestamp>/
```

保存される情報:

- 対象タスクとCodexプロンプト
- stdout、stderr、終了コード
- 検証結果
- 成功時のコミットハッシュ

長期的な検証結果はfeatureの `validation-log.md` に記録されます。

## 自律デリバリー

仕様lint、隔離worktree、実装、検証、test weakening検出、独立Codexレビュー、
push、PR作成、CI監視までをまとめて事前確認できます。

```bash
make deliver-dry-run FEATURE=012-user-login
make deliver FEATURE=012-user-login
```

リスクによる動作:

| リスク | 自動処理の上限 |
|---|---|
| low | repository policyが許可し、全ゲート成功ならPR経由で自動merge可能 |
| medium | ready-for-review PRまで作成して停止 |
| high | 原則push前に停止 |

自動mergeはfeatureの `auto_merge = true` と `.agent-policy.toml` の
`auto_merge_low_risk = true` の両方が必要です。mainへ直接pushすることは
ありません。

### Delivery smoke test

承認済みのsmoke-test仕様を、次の順番で実行します。

```bash
make spec-lint FEATURE=003-delivery-smoke-test
make deliver-dry-run FEATURE=003-delivery-smoke-test
make deliver FEATURE=003-delivery-smoke-test
make cleanup-worktree FEATURE=003-delivery-smoke-test
```

`deliver` はframework所有の隔離worktreeで実装し、機械的検証と独立した
structured reviewに合格してからpushします。その後、1件のPRを作成または更新し、
GitHub Actionsの完了まで監視します。このmedium-risk featureは自動mergeされません。
結果を確認してworktreeがcleanであることを確認した後に、最後のcleanupを実行します。

失敗状態を再開または中止扱いにする場合:

```bash
make work-resume FEATURE=012-user-login
make work-abort FEATURE=012-user-login
make cleanup-worktree FEATURE=012-user-login
```

再開時はbranch、HEAD、仕様digest、変更ファイルが保存状態と一致する必要が
あります。abortは状態を変更するだけで、差分を削除しません。
cleanupはframework所有かつcleanなworktreeだけを明示的に削除します。

## Stack adapter

```bash
make detect-stack
make init-stack STACK=python
```

Python、Node.js、Go、Rust、Android/JVM、generic Makeを検出できます。
`init-stack` は既存Makefileを上書きせず、`Makefile.<stack>.proposed` を生成します。

## 停止した場合

次の場合は自動処理を止め、人間の確認を求めます。

- main/masterまたはdirty worktree
- 同一エラーが2回連続
- タスク数・リトライ回数の上限超過
- allowed範囲外または禁止ファイルの変更
- secretやセキュリティ違反
- 仕様外の変更が必要
- 最終検証が修正上限内で成功しない

失敗時の差分は破壊的に巻き戻しません。`.agent-work/` と
`validation-log.md` を確認し、差分をレビューしてから修正または再実行します。

## Makeターゲット

| コマンド | 内容 |
|---|---|
| `make work FEATURE=<id>` | タスクを順番に自動実装する |
| `make work-dry-run FEATURE=<id>` | 変更せず実行予定を表示する |
| `make work-status FEATURE=<id>` | 進捗、次タスク、Git状態を表示する |
| `make work-resume FEATURE=<id>` | 保存状態を検証して失敗作業を再開する |
| `make work-abort FEATURE=<id>` | 差分を残して実行状態を中止にする |
| `make cleanup-worktree FEATURE=<id>` | 成功済みのcleanな隔離worktreeを削除する |
| `make spec-lint FEATURE=<id>` | 仕様とtraceabilityを機械検査する |
| `make deliver-dry-run FEATURE=<id>` | remoteを変更せずdelivery計画を表示する |
| `make deliver FEATURE=<id>` | 隔離実装、レビュー、PR、CI、リスクゲートを実行する |
| `make detect-stack` | 技術スタックと検出根拠を表示する |
| `make init-stack STACK=<name>` | Make設定案を上書きせず生成する |
| `make validate-spec FEATURE=<name>` | 必須仕様ファイルを検査する |
| `make test` | 自動化基盤とプロジェクトのテストを実行する |
| `make validate` | 全品質ゲートを実行する |

`FEATURE=012` のような番号だけでも一意なら `work` 系コマンドで解決できます。
`validate-spec` では完全なディレクトリ名を指定してください。

## 安全上の制約

- `.env`、秘密鍵、署名鍵、credentialsを読まない
- タスク本文をシェルとして実行しない
- `shell=True` を使わない
- `git push`、merge、reset、cleanを自動化しない
- テストを弱めて成功させない
- スコープや仕様の変更が必要なら停止する
- 本番設定、デプロイ、課金、認証・認可の変更は人間が承認する

詳細は `AGENTS.md`、`docs/ai-operation.md`、`docs/architecture.md` を参照して
ください。

## 開発・検証

自動化基盤のテストはPython標準ライブラリの `unittest` を使用します。

```bash
make test
make validate
```

Pull Requestでは、spec、plan、tasks、実装差分、validation logをまとめて
レビューしてください。

## Production readiness

リポジトリと認証、品質ゲート、自律deliveryの準備状態を確認します。

```bash
make doctor
make quality-check
make qualify-stacks
```

実行証跡は `.agent-work/<feature>/events.jsonl` が正本です。validation、review、
CI、mergeは同一HEAD SHAに揃わない限り合格しません。

```bash
make render-validation-log FEATURE=012-feature
```

人間がscope拡張を承認した場合は、まずpreviewします。

```bash
make approve-scope-dry-run FEATURE=012-feature PATH='prompts/**' REASON='review repair'
make approve-scope FEATURE=012-feature PATH='prompts/**' REASON='review repair'
```

version 1契約は実行されません。安全なMakeターゲットだけをversion 2へ移行します。

```bash
make migrate-contract-dry-run FEATURE=001-feature
make migrate-contract FEATURE=001-feature
```

複数featureは標準並列数1のqueueで管理できます。

```bash
make queue-add FEATURE=012-feature
make queue-status
make queue-cancel FEATURE=012-feature
```

リリース前検査はタグやGitHub Releaseを作成しません。

```bash
make release-check
```
