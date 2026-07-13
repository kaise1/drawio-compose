# drawio-compose

`drawio-compose`は、独立して編集できる複数のdraw.io moduleを、1枚の通常の`.drawio`構成図へ決定論的に合成するCLIです。

主な目的は、大規模な完成XMLをAIのコンテキストへ読み込まず、manifest、公開symbol、変更対象moduleだけで差分編集できるようにすることです。英語版の[README](README.md)を仕様の正本とします。

## Status

現在は公開v0.1 alphaです。安定版までにformatやcommandが変更される可能性があります。

## PoCの特徴

- AWSとオンプレミスを接続する、業界非依存の架空エンタープライズ構成
- 5つの単体編集可能module
- module間は`composeKey`で明示的に公開したノードだけ接続可能
- 公式draw.io shape 10,000件超をローカル検索し、候補だけをAIへ返却
- 公式mxfile XSD、参照整合性、パス安全性を検証
- 同一入力からbyte-identicalな完成XMLを生成
- AWS Application moduleの差分編集時の想定読込量は完成XMLの28.21%

## 実行例

```bash
drawio-compose validate examples/hybrid-enterprise/hybrid-enterprise.compose.xml
drawio-compose build examples/hybrid-enterprise/hybrid-enterprise.compose.xml \
  -o examples/hybrid-enterprise/build/hybrid-enterprise.drawio
drawio-compose shape-search "aws transit gateway" --limit 5 --json
```

同程度に一致するAWS shapeでは、AWS3、AWS3d、旧AWS webiconsより現在のAWS4サービスアイコンを優先します。

manifestとmoduleの詳細は[FORMAT.md](docs/FORMAT.md)を参照してください。`render`だけdraw.io Desktopを必要とし、それ以外はPythonとlxmlでヘッドレス実行できます。
