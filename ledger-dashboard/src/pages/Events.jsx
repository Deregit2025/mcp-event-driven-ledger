
import { useEffect, useState } from "react"
import { api } from "../hooks/api"
import { Card, Loading, Err } from "../components/Card"

export default function Events({ appId }) {
  const [data, setData] = useState(null)
  const [streams, setStreams] = useState(null)
  const [err, setErr] = useState(null)
  const [filter, setFilter] = useState({stream_id:"",event_type:"",limit:50})

  const load = () => {
    const p = {}
    if(filter.stream_id) p.stream_id = filter.stream_id
    if(filter.event_type) p.event_type = filter.event_type
    p.limit = filter.limit
    api.events(p).then(setData).catch(e=>setErr(e.message))
  }

  useEffect(() => {
    load()
    api.streams().then(setStreams).catch(()=>{})
  }, [])

  if (err) return <Err msg={err} />

  return (
    <div>
      <div style={{marginBottom:20}}>
        <h1 style={{fontSize:22,fontWeight:600,color:"#fff"}}>Event Store Explorer</h1>
        <p style={{fontSize:13,color:"#555",marginTop:4}}>Browse all {data?.total?.toLocaleString()||"..."} events across {streams?.streams?.length||"..."} streams</p>
      </div>

      <Card title="Filter Events">
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr auto auto",gap:10,alignItems:"end"}}>
          <div>
            <div style={{fontSize:11,color:"#555",marginBottom:4}}>Stream ID</div>
            <input value={filter.stream_id} onChange={e=>setFilter({...filter,stream_id:e.target.value})}
              style={{width:"100%",background:"#0a0c14",border:"1px solid #2a2a3a",borderRadius:6,padding:"7px 10px",color:"#e2e2e2",fontSize:12}}
              placeholder="e.g. loan-APEX-TEST-01" />
          </div>
          <div>
            <div style={{fontSize:11,color:"#555",marginBottom:4}}>Event Type</div>
            <input value={filter.event_type} onChange={e=>setFilter({...filter,event_type:e.target.value})}
              style={{width:"100%",background:"#0a0c14",border:"1px solid #2a2a3a",borderRadius:6,padding:"7px 10px",color:"#e2e2e2",fontSize:12}}
              placeholder="e.g. CreditAnalysisCompleted" />
          </div>
          <div>
            <div style={{fontSize:11,color:"#555",marginBottom:4}}>Limit</div>
            <select value={filter.limit} onChange={e=>setFilter({...filter,limit:e.target.value})}
              style={{background:"#0a0c14",border:"1px solid #2a2a3a",borderRadius:6,padding:"7px 10px",color:"#e2e2e2",fontSize:12}}>
              <option value={25}>25</option><option value={50}>50</option><option value={100}>100</option>
            </select>
          </div>
          <button onClick={load} style={{padding:"7px 20px",background:"#6c63ff",color:"#fff",border:"none",borderRadius:6,cursor:"pointer",fontSize:13}}>Search</button>
        </div>
      </Card>

      {!data ? <Loading /> : (
        <Card title={`${data.total.toLocaleString()} events found`}>
          <div style={{maxHeight:500,overflowY:"auto"}}>
            {data.events.map((e,i)=>(
              <div key={i} style={{padding:"8px 0",borderBottom:"1px solid #1e2030",fontSize:12}}>
                <div style={{display:"flex",gap:10,alignItems:"center",marginBottom:2}}>
                  <span style={{color:"#a78bfa",fontWeight:500}}>{e.event_type}</span>
                  <span style={{color:"#333",fontSize:10}}>v{e.event_version}</span>
                  <span style={{color:"#444",fontSize:10,marginLeft:"auto"}}>{e.recorded_at.substring(0,19)}</span>
                </div>
                <div style={{color:"#444",fontSize:11}}>{e.stream_id} · pos {e.stream_position} · global {e.global_position}</div>
              </div>
            ))}
          </div>
        </Card>
      )}

      <Card title="Active Streams" subtitle={`${streams?.streams?.length||0} streams`}>
        <div style={{maxHeight:300,overflowY:"auto"}}>
          {streams?.streams?.map((s,i)=>(
            <div key={i} style={{display:"flex",gap:10,padding:"6px 0",borderBottom:"1px solid #1e2030",fontSize:12,alignItems:"center"}}>
              <span style={{color:"#a78bfa",flex:1}}>{s.stream_id}</span>
              <span style={{color:"#555"}}>{s.aggregate_type}</span>
              <span style={{color:"#444"}}>v{s.current_version}</span>
              {s.is_archived && <span style={{color:"#f59e0b",fontSize:10}}>archived</span>}
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}
