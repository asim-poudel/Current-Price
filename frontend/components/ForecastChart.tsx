"use client";

import { CartesianGrid, Line, LineChart, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ForecastRow } from "@/lib/types";

const hour = (value: string) => value.slice(11, 16);

export function ForecastChart({ rows }: { rows: ForecastRow[] }) {
  const minimum = Math.min(0, ...rows.map((row) => row.predicted_price_eur_mwh));
  return (
    <div className="chart" role="img" aria-label="Line chart of the next 24 hourly electricity price forecasts">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={rows} margin={{ top: 12, right: 10, bottom: 4, left: 0 }} accessibilityLayer>
          <CartesianGrid stroke="#dce7f2" vertical={false} />
          {minimum < 0 && <ReferenceArea y1={minimum} y2={0} fill="#fee2e2" fillOpacity={0.55} />}
          <ReferenceLine y={0} stroke="#8294a8" strokeDasharray="4 4" />
          {rows.filter((row) => row.delivery_time_local.slice(11, 16) === "00:00").map((row) => (
            <ReferenceLine key={row.horizon} x={row.delivery_time_local} stroke="#8294a8" strokeDasharray="2 4" label={{ value: "DE midnight", position: "insideTopRight", fill: "#526579", fontSize: 11 }} />
          ))}
          <XAxis dataKey="delivery_time_local" tickFormatter={hour} minTickGap={24} tickLine={false} axisLine={false} />
          <YAxis width={52} tickLine={false} axisLine={false} tickFormatter={(value) => `${value}`} />
          <Tooltip labelFormatter={(value) => `Berlin ${String(value).replace("T", " ")}`} formatter={(value) => [`${Number(value).toFixed(2)} EUR/MWh`, "Forecast"]} />
          <Line isAnimationActive={false} type="monotone" dataKey="predicted_price_eur_mwh" stroke="#004e72" strokeWidth={2.5} dot={({ cx, cy, payload }) => <circle cx={cx} cy={cy} r={payload.predicted_price_eur_mwh < 0 ? 4 : 2.2} fill={payload.predicted_price_eur_mwh < 0 ? "#c73535" : "#004e72"} />} activeDot={{ r: 5 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
