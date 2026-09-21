# ループエンジニアリングの導入テンプレート

AIやコマンドに作業を依頼し、その結果を独立した検証処理で確かめます。完了条件を満たすまで繰り返し、回数・時間の上限や進展のない状態を検出して停止します。

[英語版](README.en.md) · [操作手順](docs/USAGE.md) · [設計と制約](docs/ARCHITECTURE.md)

## クローン後に試す

必要なものはGitと **Python 3.10以上** です。Pythonはこのツールを動かすために使い、対象アプリの開発言語は限定していません。付属の利用例には、追加パッケージやAPIキーは不要です。

クローンしたディレクトリで実行してください。

```sh
# 実行環境と付属の利用例を確認します
python3 kit.py doctor
python3 kit.py demo
```

Windowsでは `python3` を `py -3` へ置き換えてください。`dev.cmd` やPowerShellの `./dev.ps1` も使えます。macOS・Linuxでは `./dev` が短い呼び出し方です。

`demo` は一時的な作業場所で動きます。クローンしたテンプレートの設定や成果物を、確認済みの状態へ変更しません。

## 作業と完了条件を設定する

`.agentkit/loop.json` に依頼内容、作業を行うコマンド、検証コマンド、変更を禁止するファイル、実行上限を指定します。検証処理は、成果物を修正せずに結果を判定するものを用意してください。

```sh
# 付属の作業を実行し、保存された状態を確認します
python3 kit.py run
python3 kit.py status
```

AIへ実際に依頼する場合は、Codex・Claude Codeの設定例を使えます。ログイン済みのCLIが必要です。ほかのツールは、引数の配列で指定するコマンドとして接続します。設定方法は [AIツールとの連携](docs/INTEGRATIONS.md) に記載しています。

完了した処理を再開するときは、成果物と保存済みの検証記録を再確認します。途中で止まった処理には実行済みの操作が残ることがあるため、再試行する前に状態を確認してください。設定を変更してやり直す場合は、新しい実行として開始します。

## 自分のプロジェクトへ導入する

新しく始める場合は、空の作業場所を作成できます。

```sh
# テンプレートと実行ツールを新しい作業場所へコピーします
python3 kit.py new ../my-project
```

既存のプロジェクトへ追加する場合は、追加予定のファイルを確認してから適用します。

```sh
# 追加内容を確認してから適用します
python3 kit.py install --target ../existing-project
python3 kit.py install --target ../existing-project --apply
```

既存のAGENTS.md、CLAUDE.md、設定、フックは上書きしません。`.agentkit/loop.example.json` のパスやコマンドを実際のプロジェクトへ合わせ、`.agentkit/loop.json` として保存してください。導入先のディレクトリでは `python3 .agentkit/tools/loop/kit.py --root . inspect` で設定を確認できます。

## 設計上の範囲

このテンプレートは手元で使う開発用ツールです。ローカルの設定や記録は、利用者自身が変更できます。実行権限を制限する場合は、認証情報や実行環境側でも制御してください。詳しい対応範囲は [設計と制約](docs/ARCHITECTURE.md) に記載しています。

ツール自体を変更したときの検査は `python3 kit.py check` で実行できます。ライセンスは [MIT](LICENSE) です。第三者のコードの出典は [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) を参照してください。
