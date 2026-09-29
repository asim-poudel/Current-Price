"use client";

import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { EvaluationSeries } from "@/lib/types";

export function ComparisonChart({ rows }: { rows: EvaluationSeries["rows"] }) {
  return (
    <div className="chart chart-small" role="img" aria-label="Line chart comparing the previous forecast with observed prices">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={rows} margin={{ top: 10, right: 10, bottom: 4, left: 0 }} accessibilityLayer>
          <CartesianGrid stroke="#dce7f2" vertical={false} />
          <ReferenceLine y={0} stroke="#8294a8" strokeDasharray="4 4" />
          <XAxis dataKey="delivery_time_local" tickFormatter={(value) => String(value).slice(11, 16)} minTickGap={24} tickLine={false} axisLine={false} />
          <YAxis width={52} tickLine={false} axisLine={false} />
          <Tooltip formatter={(value, name) => [`${Number(value).toFixed(2)} EUR/MWh`, name === "actual_price_eur_mwh" ? "Actual" : "Forecast"]} />
          <Line isAnimationActive={false} type="monotone" dataKey="predicted_price_eur_mwh" stroke="#004e72" strokeWidth={2} dot={false} />
          <Line isAnimationActive={false} type="monotone" dataKey="actual_price_eur_mwh" stroke="#d28a19" strokeWidth={2} dot={false} connectNulls={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
