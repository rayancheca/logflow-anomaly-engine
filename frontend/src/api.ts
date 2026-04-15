export async function triggerScenario(name: string): Promise<boolean> {
  const res = await fetch(`/api/scenarios/${name}`, { method: "POST" });
  if (!res.ok) return false;
  const data = (await res.json()) as { ok: boolean };
  return data.ok;
}

export async function listScenarios(): Promise<string[]> {
  const res = await fetch("/api/scenarios");
  if (!res.ok) return [];
  const d = (await res.json()) as { scenarios: string[] };
  return d.scenarios;
}
