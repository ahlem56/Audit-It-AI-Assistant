import { useEffect, useMemo, useState } from 'react';
import { fetchObservations } from '../services/api';
import type { Observation, PriorityLevel } from '../types';

export function useObservations() {
  const [observations, setObservations] = useState<Observation[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<'All' | 'Draft' | 'Validated'>('All');
  const [priorityFilter, setPriorityFilter] = useState<'All' | PriorityLevel>('All');
  const [applicationFilter, setApplicationFilter] = useState<'All' | string>('All');

  useEffect(() => {
    fetchObservations()
      .then((data) => setObservations(data))
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => {
    return observations.filter((obs) => {
      const matchesSearch = [obs.control_id, obs.application, obs.finding, obs.comments]
        .join(' ')
        .toLowerCase()
        .includes(search.toLowerCase());
      const matchesStatus = statusFilter === 'All' || obs.status === statusFilter;
      const matchesPriority = priorityFilter === 'All' || obs.priority === priorityFilter;
      const matchesApplication = applicationFilter === 'All' || obs.application === applicationFilter;
      return matchesSearch && matchesStatus && matchesPriority && matchesApplication;
    });
  }, [observations, search, statusFilter, priorityFilter, applicationFilter]);

  const summary = useMemo(() => {
    const totals = { Critical: 0, High: 0, Medium: 0, Low: 0 } as Record<PriorityLevel, number>;
    observations.forEach((obs) => {
      totals[obs.priority] += 1;
    });
    return {
      total: observations.length,
      counts: totals
    };
  }, [observations]);

  return {
    observations,
    setObservations,
    filtered,
    loading,
    search,
    setSearch,
    statusFilter,
    setStatusFilter,
    priorityFilter,
    setPriorityFilter,
    applicationFilter,
    setApplicationFilter,
    summary
  };
}
