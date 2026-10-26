"""Cross-validated accuracy of the bill classifier.

Usage (from the backend folder):  python -m app.evaluation.classifier_eval

Reports the model alone and the full hybrid (rules + model), using 5-fold
cross-validation on app/data/bill_training.csv. The training lines are written
examples, so add lines from real bills to get an honest number.
"""

from collections import Counter

from sklearn.model_selection import StratifiedKFold

from app.engine.classifier import build_model, categorize, training_data


def cross_validate(folds: int = 5, seed: int = 0) -> dict[str, object]:
    texts, labels = training_data()
    model_hits = hybrid_hits = 0
    per_class_total: Counter[str] = Counter()
    per_class_hits: Counter[str] = Counter()
    splitter = StratifiedKFold(n_splits=folds, shuffle=True, random_state=seed)
    for train_idx, test_idx in splitter.split(texts, labels):
        model = build_model().fit([texts[i] for i in train_idx], [labels[i] for i in train_idx])
        for i in test_idx:
            truth = labels[i]
            model_hits += model.predict([texts[i]])[0] == truth
            hybrid = categorize(texts[i], model)[0].value
            hybrid_hits += hybrid == truth
            per_class_total[truth] += 1
            per_class_hits[truth] += hybrid == truth
    n = len(texts)
    return {
        "lines": n,
        "model_accuracy": round(model_hits / n, 3),
        "hybrid_accuracy": round(hybrid_hits / n, 3),
        "per_category": {c: round(per_class_hits[c] / per_class_total[c], 3) for c in sorted(per_class_total)},
    }


def main() -> int:
    r = cross_validate()
    print(f"Bill classifier, 5-fold cross-validation on {r['lines']} labelled lines")
    print(f"  model only:      {r['model_accuracy']:.1%}")
    print(f"  rules + model:   {r['hybrid_accuracy']:.1%}")
    for cat, acc in r["per_category"].items():
        print(f"    {cat:18} {acc:.1%}")
    print("Note: these lines were written as examples. Add lines from real bills for a real-world number.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
