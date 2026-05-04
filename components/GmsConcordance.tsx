/**
 * GmsConcordance — visual representation of GMS lab classification concordance.
 *
 * Displays a row of 5 rounded squares where each square represents one GMS lab:
 *   - Green  (#22c55e) = oncogenic / pathogenic classification
 *   - Yellow (#facc15) = benign classification
 *   - Grey   (#d1d5db) = not yet classified
 *
 * Props:
 *   value — [oncogenic, benign, unknown] integer tuple summing to 5, or null
 */

interface Props {
  value: [number, number, number] | null;
}

const SIZE = 14;
const GAP = 3;
const RADIUS = 3;
const TOTAL = 5;

const COLOR_ONCOGENIC = "#22c55e";
const COLOR_BENIGN    = "#facc15";
const COLOR_UNKNOWN   = "#d1d5db";

export default function GmsConcordance({ value }: Props) {
  if (!value) return <span className="text-gray-300">—</span>;

  const [onc, ben, unk] = value;

  // Build ordered array of colours: oncogenic first, then benign, then unknown
  const colours: string[] = [
    ...Array(onc).fill(COLOR_ONCOGENIC),
    ...Array(ben).fill(COLOR_BENIGN),
    ...Array(unk).fill(COLOR_UNKNOWN),
  ].slice(0, TOTAL);

  const width = TOTAL * SIZE + (TOTAL - 1) * GAP;
  const height = SIZE;

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      aria-label={`GMS: ${onc} oncogenic, ${ben} benign, ${unk} unclassified`}
      role="img"
    >
      {colours.map((fill, i) => (
        <rect
          key={i}
          x={i * (SIZE + GAP)}
          y={0}
          width={SIZE}
          height={SIZE}
          rx={RADIUS}
          ry={RADIUS}
          fill={fill}
          stroke={fill === COLOR_UNKNOWN ? "#9ca3af" : "none"}
          strokeWidth={fill === COLOR_UNKNOWN ? 1 : 0}
        />
      ))}
    </svg>
  );
}
