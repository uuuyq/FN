export const trainingParts = ["胸", "背", "腿", "二头", "三头", "肩", "腹"];
export function TrainingParts({ parts }: { parts: string[] }) {
  return (
    <span className="training-parts">
      {trainingParts
        .filter((part) => parts.includes(part))
        .map((part) => (
          <span
            key={part}
            className={`training-part part-${trainingParts.indexOf(part)}`}
          >
            {part}
          </span>
        ))}
    </span>
  );
}
