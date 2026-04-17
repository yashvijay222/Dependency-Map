from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
from torch.optim import AdamW
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModelForSequenceClassification, AutoTokenizer


@dataclass(slots=True)
class TrainingExample:
    example_id: str
    input_text: str
    label: int
    label_text: str
    metadata: dict[str, Any]


class GraphCodeBERTDataset(Dataset[TrainingExample]):
    def __init__(self, examples: list[TrainingExample]) -> None:
        self.examples = examples

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, index: int) -> TrainingExample:
        return self.examples[index]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python scripts/train_graphcodebert.py")
    parser.add_argument("--train", required=True, help="Path to graphcodebert-train.jsonl")
    parser.add_argument("--val", required=True, help="Path to graphcodebert-val.jsonl")
    parser.add_argument("--out-dir", required=True, help="Directory to save checkpoints")
    parser.add_argument(
        "--model-name",
        default="microsoft/graphcodebert-base",
        help="Hugging Face model checkpoint",
    )
    parser.add_argument("--epochs", type=int, default=3, help="Number of training epochs")
    parser.add_argument("--batch-size", type=int, default=4, help="Mini-batch size")
    parser.add_argument("--learning-rate", type=float, default=2e-5, help="AdamW learning rate")
    parser.add_argument("--max-length", type=int, default=512, help="Tokenizer max sequence length")
    parser.add_argument("--weight-decay", type=float, default=0.01, help="AdamW weight decay")
    parser.add_argument("--seed", type=int, default=7, help="Random seed")
    parser.add_argument("--device", help="Override torch device, e.g. cpu or cuda")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    torch.manual_seed(int(args.seed))

    train_examples = load_examples(Path(args.train))
    val_examples = load_examples(Path(args.val))
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    tokenizer = AutoTokenizer.from_pretrained(args.model_name)
    model = AutoModelForSequenceClassification.from_pretrained(
        args.model_name,
        num_labels=2,
    )
    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)

    train_loader = build_dataloader(
        GraphCodeBERTDataset(train_examples),
        tokenizer,
        batch_size=int(args.batch_size),
        max_length=int(args.max_length),
        shuffle=True,
    )
    val_loader = build_dataloader(
        GraphCodeBERTDataset(val_examples),
        tokenizer,
        batch_size=int(args.batch_size),
        max_length=int(args.max_length),
        shuffle=False,
    )

    optimizer = AdamW(
        model.parameters(),
        lr=float(args.learning_rate),
        weight_decay=float(args.weight_decay),
    )

    best_val_loss = math.inf
    history: list[dict[str, Any]] = []
    for epoch in range(1, int(args.epochs) + 1):
        train_metrics = run_epoch(model, train_loader, optimizer, device=device, train=True)
        val_metrics = run_epoch(model, val_loader, optimizer, device=device, train=False)
        epoch_metrics = {
            "epoch": epoch,
            "train_loss": train_metrics["loss"],
            "train_accuracy": train_metrics["accuracy"],
            "val_loss": val_metrics["loss"],
            "val_accuracy": val_metrics["accuracy"],
        }
        history.append(epoch_metrics)
        if val_metrics["loss"] < best_val_loss:
            best_val_loss = val_metrics["loss"]
            save_checkpoint(model, tokenizer, out_dir / "best-checkpoint")

    save_checkpoint(model, tokenizer, out_dir / "last-checkpoint")
    summary = {
        "model_name": args.model_name,
        "device": device,
        "train_examples": len(train_examples),
        "val_examples": len(val_examples),
        "epochs": int(args.epochs),
        "batch_size": int(args.batch_size),
        "learning_rate": float(args.learning_rate),
        "history": history,
        "best_val_loss": best_val_loss,
    }
    (out_dir / "training-summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return 0


def load_examples(path: Path) -> list[TrainingExample]:
    rows: list[TrainingExample] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        rows.append(
            TrainingExample(
                example_id=str(payload["example_id"]),
                input_text=str(payload["input_text"]),
                label=int(payload["label"]),
                label_text=str(payload.get("label_text") or ""),
                metadata=dict(payload.get("metadata") or {}),
            )
        )
    return rows


def build_dataloader(
    dataset: GraphCodeBERTDataset,
    tokenizer: Any,
    *,
    batch_size: int,
    max_length: int,
    shuffle: bool,
) -> DataLoader[dict[str, Any]]:
    def collate_fn(batch: list[TrainingExample]) -> dict[str, Any]:
        texts = [item.input_text for item in batch]
        labels = torch.tensor([item.label for item in batch], dtype=torch.long)
        encoded = tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=max_length,
            return_tensors="pt",
        )
        encoded["labels"] = labels
        encoded["example_ids"] = [item.example_id for item in batch]
        return encoded

    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        collate_fn=collate_fn,
    )


def run_epoch(
    model: Any,
    dataloader: DataLoader[dict[str, Any]],
    optimizer: AdamW,
    *,
    device: str,
    train: bool,
) -> dict[str, float]:
    if train:
        model.train()
    else:
        model.eval()

    total_loss = 0.0
    total_examples = 0
    correct = 0
    for batch in dataloader:
        labels = batch.pop("labels").to(device)
        batch.pop("example_ids", None)
        inputs = {key: value.to(device) for key, value in batch.items()}
        if train:
            optimizer.zero_grad(set_to_none=True)
        with torch.set_grad_enabled(train):
            outputs = model(**inputs, labels=labels)
            loss = outputs.loss
            logits = outputs.logits
        if train:
            loss.backward()
            optimizer.step()

        predictions = logits.argmax(dim=-1)
        batch_size = int(labels.size(0))
        total_loss += float(loss.item()) * batch_size
        total_examples += batch_size
        correct += int((predictions == labels).sum().item())

    mean_loss = total_loss / max(total_examples, 1)
    accuracy = correct / max(total_examples, 1)
    return {
        "loss": round(mean_loss, 4),
        "accuracy": round(accuracy, 4),
    }


def save_checkpoint(model: Any, tokenizer: Any, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(out_dir)
    tokenizer.save_pretrained(out_dir)


if __name__ == "__main__":
    raise SystemExit(main())
