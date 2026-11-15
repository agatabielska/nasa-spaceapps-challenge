"""Plot the completed run's training history and write a result comparison."""
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/".deps")); os.environ.setdefault("MPLCONFIGDIR",str(ROOT/"outputs/.matplotlib"))
import numpy as np
import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt

out=ROOT/"outputs/etna"
rows=[json.loads(line) for line in (out/"run.jsonl").read_text().splitlines()]
# Last full training session, excluding earlier smoke run.
starts=[i for i,r in enumerate(rows) if r["event"]=="start" and r.get("stage")=="train"]
rows=rows[starts[-1]:]
training=[r for r in rows if r["event"]=="training"]
validation=[r for r in rows if r["event"]=="validation"]
fig,axes=plt.subplots(1,2,figsize=(12,4))
axes[0].plot([r["step"] for r in training],[r["total"] for r in training],label="Training (256×256)")
axes[0].plot([r["step"] for r in validation],[r["total"] for r in validation],"o-",label="Held-out (128×128)")
axes[0].set_ylabel("Translation objective"); axes[0].set_xlabel("Optimizer update"); axes[0].legend()
axes[0].set_title("Checkpoint comparison uses the fixed validation set")
for name in ["style","content"]:
    values=[r[name]*(1000 if name=="content" else 1) for r in validation]
    axes[1].plot([r["step"] for r in validation],values,"o-",label=name+(" ×1000" if name=="content" else ""))
axes[1].set_xlabel("Optimizer update"); axes[1].set_ylabel("Held-out objective components"); axes[1].legend()
fig.suptitle("These objectives are not change-detection accuracy metrics")
fig.tight_layout(); fig.savefig(out/"training_history.png",dpi=150); plt.close(fig)
methods={name:json.loads((out/path/"study.json").read_text()) for name,path in
         [("UCDFormer","."),("no_translation","no_translation"),("log_change_otsu","baseline")]}
comparison={key:dict(changed_fraction=r["changed_fraction"],valid_area_km2=r["valid_area_km2"],
                    changed_area_km2=r["changed_area_km2"]) for key,r in methods.items()}
comparison["caveat"]="Method agreement and changed area are diagnostics, not accuracy. Baseline has more valid coverage; compare on common support for quantitative agreement."
(out/"method_comparison.json").write_text(json.dumps(comparison,indent=2)+"\n")
summary=json.loads((out/"training_summary.json").read_text())
report=methods["UCDFormer"]
text=f'''# Etna: first executed UCDFormer SAR adaptation

Inputs: July 23 and August 16, 2026; HH/HV GCOV, 20 m UTM zone 33N. Approximately 10×10 km around the summit. See [per-polarization EDA](../eda/etna/README.md) for physical changes and event chronology.

## What ran

Three named features (HH dB, HV dB, their dB difference), shared training-strip scaling, original optical VGG/StyleFormer/decoder initialization, scene-pair translation adaptation, VGG feature differences, strict FCM/adaptive pseudo-label agreement and final RF classification. Checkpoint initialization loaded strictly with no translator/decoder tensor mismatch. Raw-dot content affinity follows actual repository code, despite its cosine naming; near-zero denominators are guarded. Gradient norm clipped at 100.

Training stopped at {summary["updates"]} updates; selected update {summary["best_step"]}. Held-out translation objective: {summary["initial_validation"]:.4f} initially → {summary["best_validation"]:.4f} best. This is not detection accuracy. Five overlapping training windows are drawn from the northern strip; three 128-pixel validation windows lie in the southern strip, separated by a 114-pixel moat. Training and validation patch fields of view differ, so their losses should not be compared as equal-scale generalization error. Checkpoints are compared on the same validation windows.

## Results and practical limits

Model-supported coverage: {report["details"]["model_supported_fraction"]:.2%}. Changed fraction of that supported coverage: {report["changed_fraction"]:.2%}. These are algorithm outputs, not verified event extent.

The conservative model path accepts fully valid inference tiles. One invalid native pixel at row 464/column 442 excludes a larger bottom-right tile region, leaving about 5.3% unsupported; white/transparent areas are nodata, not unchanged. Full physical EDA still covers all valid native pixels. Resolving that unsupported area requires a reviewed inference-context/mask strategy.

Only {report["details"]["changed_seeds"]} confident changed seeds trained the RF against balanced unchanged samples. The RF extrapolates beyond those seeds; this needs independent inspection. The output also flags broad terrain/texture-related areas. It is a prototype, not a validated lava or damage map. Translation did not eliminate every nuisance change. A no-translation result and a physical Otsu baseline are saved for comparison.

No independent reference labels were available; no F1, IoU or accuracy is claimed. Before/after chronology establishes an observation interval, not that every flagged pixel was caused by volcanic activity.

![Run history](training_history.png)

![Four-panel result](overview.png)

## Files for the app

- [study.json](study.json): method, sources, geographic bounds, valid/changed area and limitations.
- [Binary GeoTIFF](change_mask.tif): 0 unchanged, 1 changed, 255 nodata; native projected CRS.
- [Continuous score](change_score.tif): raw uncalibrated feature score.
- `before_wgs84.png`, `after_wgs84.png`, `mask_wgs84.png`, `overlay_wgs84.png`: geographic display assets using the bounds in study.json.
- `best.pt`, `random_forest.joblib`, `effective_config.json`, `pair_metadata.json`, `run.jsonl`: initialization, adaptation and output provenance.

New timestamp pairs require their own preprocessing and may need translation/RF adaptation. This run does not establish an instant reusable cross-event model.
'''
(out/"README.md").write_text(text)
print("Saved training history, method comparison and result caveats")
