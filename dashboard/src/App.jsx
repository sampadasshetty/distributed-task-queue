import { useState, useEffect } from 'react';
import axios from 'axios';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from 'recharts';
import './App.css';

const API_URL = 'http://localhost:8000';

function App() {
  const [stats, setStats] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 2000);
    return () => clearInterval(interval);
  }, []);

  const fetchData = async () => {
    try {
      const statsRes = await axios.get(`${API_URL}/stats`);
      const jobsRes = await axios.get(`${API_URL}/jobs?per_page=50`);

      setStats(statsRes.data);
      setJobs(jobsRes.data.jobs);
      setError(null);
    } catch (err) {
      setError('Cannot reach API. Is uvicorn running?');
    }
  };

  const retryJob = async (jobId) => {
    try {
      await axios.post(`${API_URL}/jobs/${jobId}/retry`);
      fetchData();
    } catch (err) {
      alert('Retry failed: ' + err.response?.data?.detail);
    }
  };

  if (error) {
    return <div className="error-screen">{error}</div>;
  }

  if (!stats) {
    return <div className="loading-screen">Loading...</div>;
  }

  const barData = [
    { name: 'Pending', value: stats.pending },
    { name: 'Running', value: stats.running },
    { name: 'Success', value: stats.success },
    { name: 'Failed', value: stats.failed },
    { name: 'Dead', value: stats.dead },
  ];

  const pieData = [
    { name: 'Success', value: stats.success, color: '#10b981' },
    { name: 'Failed', value: stats.failed, color: '#f59e0b' },
    { name: 'Dead', value: stats.dead, color: '#ef4444' },
    { name: 'Pending', value: stats.pending, color: '#6b7280' },
    { name: 'Running', value: stats.running, color: '#3b82f6' },
  ];

  const statusColors = {
    PENDING: '#475569',
    RUNNING: '#3b82f6',
    SUCCESS: '#10b981',
    FAILED: '#f59e0b',
    DEAD: '#ef4444',
  };

  return (
    <div className="app">
      {/* Header */}
      <div className="header">
        <div>
          <h1>Distributed Task Queue</h1>
          <div className="subtitle">
            <span className="live-dot"></span>
            Live · refreshes every 2s
          </div>
        </div>
      </div>

      {/* Cards */}
      <div className="cards">
        <div className="card" style={{ '--accent': '#3b82f6' }}>
          <div className="card-label">Total Jobs</div>
          <div className="card-value">{stats.total_jobs}</div>
        </div>

        <div className="card" style={{ '--accent': '#a78bfa' }}>
          <div className="card-label">Queue Length</div>
          <div className="card-value">{stats.queue_length}</div>
        </div>

        <div className="card" style={{ '--accent': '#f87171' }}>
          <div className="card-label">Dead Letter Queue</div>
          <div className="card-value danger">
            {stats.dead_letter_length}
          </div>
        </div>

        <div className="card" style={{ '--accent': '#34d399' }}>
          <div className="card-label">Success Rate</div>
          <div className="card-value success">
            {stats.total_jobs > 0
              ? Math.round((stats.success / stats.total_jobs) * 100)
              : 0}
            %
          </div>
        </div>
      </div>

      {/* Charts */}
      <div className="charts">
        <div className="chart-box">
          <h3>Job Status Breakdown</h3>

          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={barData}>
              <XAxis dataKey="name" stroke="#888" />
              <YAxis stroke="#888" />
              <Tooltip />
              <Bar
                dataKey="value"
                fill="#3b82f6"
                radius={[4, 4, 0, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="chart-box">
          <h3>Distribution</h3>

          <ResponsiveContainer width="100%" height={250}>
            <PieChart>
              <Pie
                data={pieData.filter((d) => d.value > 0)}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                outerRadius={80}
                label
              >
                {pieData.map((entry, index) => (
                  <Cell key={index} fill={entry.color} />
                ))}
              </Pie>

              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Jobs Table */}
      <div className="table-section">
        <h3>Recent Jobs</h3>

        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Status</th>
              <th>Priority</th>
              <th>Retries</th>
              <th>Worker</th>
              <th>Created</th>
              <th>Action</th>
            </tr>
          </thead>

          <tbody>
            {jobs.map((job) => (
              <tr key={job.id}>
                <td>{job.name}</td>

                <td>
                  <span
                    className="status-badge"
                    style={{
                      backgroundColor: statusColors[job.status],
                    }}
                  >
                    {job.status}
                  </span>
                </td>

                <td>
                  <span
                    className={`priority-tag priority-${job.priority}`}
                  >
                    {job.priority}
                  </span>
                </td>

                <td>
                  {job.retry_count}/{job.max_retries}
                </td>

                <td>{job.worker_id || '-'}</td>

                <td>
                  {new Date(job.created_at).toLocaleTimeString()}
                </td>

                <td>
                  {(job.status === 'FAILED' ||
                    job.status === 'DEAD') && (
                    <button onClick={() => retryJob(job.id)}>
                      Retry
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default App;