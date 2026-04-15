import { useMemo } from 'react';
import { Bar, BarChart, Cell, Pie, PieChart, ResponsiveContainer } from 'recharts';
import { RefreshCcw } from 'lucide-react';
import { useMissionContext } from '../context/MissionContext';

const processCounts = [
  { process: 'APD', count: 4 },
  { process: 'PC', count: 2 },
  { process: 'CO', count: 2 }
];

const heatmapMatrix = [
  { app: 'SAP', APD: 2, PC: 1, CO: 1 },
  { app: 'Oracle', APD: 1, PC: 2, CO: 1 },
  { app: 'Active Directory', APD: 1, PC: 0, CO: 1 }
];

const priorityColors = {
  Critical: '#FCA5A5',
  High: '#FDBA74',
  Medium: '#FDE68A',
  Low: '#86EFAC'
};

export default function DashboardPage() {
  const { activeMission, observations, loadingObservations } = useMissionContext();

  if (!activeMission) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <p className="text-slate-500">Please select a mission from the workspace first.</p>
      </div>
    );
  }

  const priorityData = useMemo(() => {
    const totals = { Critical: 0, High: 0, Medium: 0, Low: 0 } as Record<string, number>;
    observations.forEach((obs) => {
      totals[obs.priority] += 1;
    });
    return Object.entries(totals).map(([name, value]) => ({ name, value }));
  }, [observations]);

  const validatedCount = useMemo(() => observations.filter((obs) => obs.status === 'Validated').length, [observations]);

  const topRisks = useMemo(() => observations.slice(0, 5), [observations]);

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <p className="text-sm uppercase tracking-[0.2em] text-slate-500">Analytics</p>
          <h1 className="text-3xl font-semibold text-slate-900">{activeMission?.name} dashboard</h1>
          <p className="mt-2 text-sm text-slate-600">Live overview of observations, risk distribution, and validation progress for the current mission.</p>
        </div>
        <button className="inline-flex items-center gap-2 rounded-2xl bg-white px-4 py-2 text-sm font-semibold text-slate-700 shadow-sm ring-1 ring-slate-200 hover:bg-slate-50">
          <RefreshCcw className="h-4 w-4" /> Refresh
        </button>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-card">
          <p className="text-sm text-slate-500">Total observations</p>
          <p className="mt-4 text-3xl font-semibold text-slate-900">{observations.length}</p>
        </div>
        <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-card">
          <p className="text-sm text-slate-500">Critical count</p>
          <p className="mt-4 text-3xl font-semibold text-red-600">{observations.filter((obs) => obs.priority === 'Critical').length}</p>
        </div>
        <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-card">
          <p className="text-sm text-slate-500">High count</p>
          <p className="mt-4 text-3xl font-semibold text-orange-600">{observations.filter((obs) => obs.priority === 'High').length}</p>
        </div>
        <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-card">
          <p className="text-sm text-slate-500">Validated progress</p>
          <p className="mt-4 text-3xl font-semibold text-slate-900">{validatedCount}/{observations.length}</p>
          <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-200">
            <div className="h-full rounded-full bg-emerald-500" style={{ width: `${(validatedCount / Math.max(observations.length, 1)) * 100}%` }} />
          </div>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-[0.85fr_0.65fr]">
        <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-card">
          <div className="mb-6 flex items-center justify-between">
            <div>
              <p className="text-sm text-slate-500">Priority distribution</p>
              <h2 className="mt-2 text-lg font-semibold text-slate-900">Observation severity</h2>
            </div>
          </div>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={priorityData} dataKey="value" innerRadius={60} outerRadius={100} paddingAngle={4}>
                  {priorityData.map((entry) => (
                    <Cell key={entry.name} fill={priorityColors[entry.name as keyof typeof priorityColors]} />
                  ))}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-card">
          <div className="mb-6">
            <p className="text-sm text-slate-500">Top 5 risks</p>
            <h2 className="mt-2 text-lg font-semibold text-slate-900">Highest priority observations</h2>
          </div>
          <div className="space-y-4">
            {topRisks.map((obs, index) => (
              <div key={obs.id} className="rounded-3xl border border-slate-200 p-4">
                <p className="text-xs uppercase tracking-[0.2em] text-slate-400">#{index + 1}</p>
                <p className="mt-2 font-semibold text-slate-900">{obs.control_id} — {obs.application}</p>
                <p className="mt-2 text-sm text-slate-600 line-clamp-2">{obs.finding}</p>
                <div className="mt-3 flex items-center gap-3 text-xs font-semibold text-slate-700">
                  <span className="rounded-full bg-red-100 px-2 py-1 text-red-700">{obs.priority}</span>
                  <span className="text-slate-500">{obs.status}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-[0.8fr_0.6fr]">
        <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-card">
          <div className="mb-6 flex items-center justify-between">
            <div>
              <p className="text-sm text-slate-500">Process review</p>
              <h2 className="mt-2 text-lg font-semibold text-slate-900">Observations by process</h2>
            </div>
          </div>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={processCounts} margin={{ left: -20, right: 0 }}>
                <Bar dataKey="count" radius={[12, 12, 0, 0]}>
                  {processCounts.map((entry) => (
                    <Cell key={entry.process} fill="#2563EB" />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-card">
          <p className="text-sm text-slate-500">Heatmap</p>
          <h2 className="mt-2 text-lg font-semibold text-slate-900">Applications vs control processes</h2>
          <div className="mt-6 overflow-hidden rounded-3xl border border-slate-200">
            <table className="w-full border-collapse text-sm">
              <thead className="bg-slate-50 text-slate-500">
                <tr>
                  <th className="border-b border-slate-200 px-4 py-3 text-left">Application</th>
                  <th className="border-b border-slate-200 px-4 py-3">APD</th>
                  <th className="border-b border-slate-200 px-4 py-3">PC</th>
                  <th className="border-b border-slate-200 px-4 py-3">CO</th>
                </tr>
              </thead>
              <tbody>
                {heatmapMatrix.map((row) => (
                  <tr key={row.app} className="border-b border-slate-200 last:border-0">
                    <td className="px-4 py-3 text-slate-700">{row.app}</td>
                    {(['APD', 'PC', 'CO'] as const).map((key) => {
                      const count = row[key];
                      const shade = count === 0 ? 'bg-slate-100 text-slate-500' : count === 1 ? 'bg-amber-100 text-amber-800' : 'bg-orange-100 text-orange-800';
                      return (
                        <td key={key} className="px-4 py-3 text-center">
                          <span className={`inline-flex min-w-[48px] items-center justify-center rounded-full px-2 py-1 text-xs font-semibold ${shade}`}>{count}</span>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
