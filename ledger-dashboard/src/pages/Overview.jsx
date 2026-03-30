
import { useEffect, useState } from "react"
import { api } from "../hooks/api"
import { Card, Stat, Loading, Err, Badge } from "../components/Card"
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts"

export default function Overview({ appId }) {
  const [data, setData] = useState(null)
  const [health, setHealth] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    Promise.all([api.stats(), api.health()])
      .then(([s, h]) => { setData(s); setHealth(h) })
      .catch(e => setErr(e.message))
  }, [])

  if (err) return <Err msg={err} />
  if (!data) return <Loading />

  const pieData = [
    { name: "Approved", value: data.decisions.approved },
    { name: "Declined", value: data.decisions.declined },
  ]
  const COLORS = ["#22c55e", "#ef4444"]

  return (
    <div>
      <div style={{marginBottom:20}}>
        <h1 style={{fontSize:22,fontWeight:600,color:"#fff"}}>Apex Ledger Overview</h1>
        <p style={{fontSize:13,color:"#555",marginTop:4}}>Production event store — {data.total_events.toLocaleString()} events across {data.total_streams} streams</p>
      </div>

      <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:16,marginBottom:16}}>
        <Card><Stat value={data.total_events.toLocaleString()} label="Total Events" /></Card>
        <Card><Stat value={data.total_streams} label="Active Streams" color="#60a5fa" /></Card>
        <Card><Stat value={data.decisions.approved} label="Approved" color="#22c55e" /></Card>
        <Card><Stat value={data.decisions.declined} label="Declined" color="#ef4444" /></Card>
      </div>

      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:16,marginBottom:16}}>
        <Card title="Top Event Types" subtitle="Most frequent events in the store">
          {data.top_event_types.map((t,i) => (
            <div key={i} style={{display:"flex",justifyContent:"space-between",alignItems:"center",padding:"6px 0",borderBottom:"1px solid #1e2030",fontSize:12}}>
              <span style={{color:"#a78bfa"}}>{t.type}</span>
              <span style={{color:"#555"}}>{t.count}</span>
            </div>
          ))}
        </Card>

        <Card title="Decision Outcomes">
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie data={pieData} cx="50%" cy="50%" outerRadius={70} dataKey="value" label={({name,value})=>`${name}: ${value}`}>
                {pieData.map((_, i) => <Cell key={i} fill={COLORS[i]} />)}
              </Pie>
              <Tooltip contentStyle={{background:"#16192a",border:"1px solid #2a2a3a",color:"#e2e2e2"}} />
            </PieChart>
          </ResponsiveContainer>
        </Card>
      </div>

      <Card title="Recent Activity" subtitle="Last 10 events across all streams">
        {data.recent_events.map((e,i) => (
          <div key={i} style={{display:"flex",gap:12,padding:"7px 0",borderBottom:"1px solid #1e2030",fontSize:12,alignItems:"center"}}>
            <span style={{color:"#a78bfa",minWidth:220}}>{e.event_type}</span>
            <span style={{color:"#444",flex:1}}>{e.stream_id}</span>
            <span style={{color:"#555"}}>{e.recorded_at.substring(0,19)}</span>
          </div>
        ))}
      </Card>
    </div>
  )
}
