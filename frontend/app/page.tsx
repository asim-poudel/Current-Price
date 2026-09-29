import { Dashboard } from "@/components/Dashboard";
import { getDashboardData } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function Home() {
  const data = await getDashboardData();
  return <Dashboard {...data} />;
}
