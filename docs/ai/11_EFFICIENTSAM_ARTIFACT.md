# EfficientSAM-Ti ONNX Artifact

P0のSegmentationは、[yformer/EfficientSAM](https://github.com/yformer/EfficientSAM) が案内する
公式ONNX版 `efficientsam_ti.onnx` を使う。公式のONNX入力例は
`EfficientSAM_onnx_example.py` に従い、`batched_images` とBoxの二隅（labels `2`, `3`）を渡す。

RuntimeでのDownloadは禁止する。PoC/Deploy前に、Repository rootで次を実行する。

```powershell
uv --directory backend run python ../scripts/fetch_efficientsam_onnx.py
```

PoCで取得・確認したSHA-256は以下。Deployではこの値を再検証し、違うartifactを使う場合は
新しい値と理由を記録する。

```text
143c3198a7b2a15f23c21cdb723432fb3fbcdbabbdad3483cf3babd8b95c1397
```

```powershell
uv --directory backend run python ../scripts/fetch_efficientsam_onnx.py --sha256 143c3198a7b2a15f23c21cdb723432fb3fbcdbabbdad3483cf3babd8b95c1397
docker build --target real-ai -t omoi-backend-real .
```

Artifactは `backend/.models/efficientsam_ti.onnx` にのみ置き、Gitへcommitしない。`real-ai`
targetはこのArtifactを `/srv/models/efficientsam_ti.onnx` へコピーして `EFFICIENTSAM_MODEL_PATH`
を設定する。PyTorchはRuntime dependencyではない。
