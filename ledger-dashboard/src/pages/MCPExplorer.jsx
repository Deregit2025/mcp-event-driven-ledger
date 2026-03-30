
import { useEffect, useState } from "react"
import { api } from "../hooks/api"
import { Card, Loading, Err } from "../components/Card"

export default function MCPExplorer({ appId }) {
  const [tools, setTools] = useState(null)
  const [resources, setResources] = useState(null)
  const [err, setErr] = useState(null)
  const [selected, setSelected] = useState(null)

  useEffect(() => {
    Promise.all([api.mcpTools(), api.mcpResources()])
      .then(([t,r])=>{ setTools(t); setResources(r) })
      .catch(e=>setErr(e.message))
  }, [])

  if (err) return <Err msg={err} />
  if (!tools) return <Loading />

  return (
    <div>
      <div style={{marginBottom:20}}>
        <h1 style={{fontSize:22,fontWeight:600,color:"#fff"}}>MCP Explorer</h1>
        <p style={{fontSize:13,color:"#555",marginTop:4}}>{tools.total} tools (write side) · {resources.total} resources (read side)</p>
      </div>

      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:16}}>
        <Card title="MCP Tools — Write Side" subtitle="Commands that append events to the store">
          {tools.tools.map((t,i)=>(
            <div key={i} onClick={()=>setSelected(selected?.name===t.name?null:t)}
              style={{padding:"10px 12px",borderRadius:6,border:"1px solid #2a2a3a",background:selected?.name===t.name?"#1e1a3a":"#0f1117",marginBottom:6,cursor:"pointer",transition:"all 0.2s"}}>
              <div style={{fontSize:13,fontWeight:500,color:"#d97706",marginBottom:4}}>{t.name}</div>
              <div style={{fontSize:11,color:"#555",lineHeight:1.5}}>{t.description.substring(0,120)}...</div>
              {selected?.name===t.name && (
                <div style={{marginTop:10,padding:10,background:"#0a0c14",borderRadius:6}}>
                  <div style={{fontSize:11,color:"#a78bfa",marginBottom:6}}>Required fields:</div>
                  {t.inputSchema?.required?.map(r=>(
                    <span key={r} style={{display:"inline-block",margin:"2px 4px 2px 0",padding:"1px 8px",background:"#1e1a3a",borderRadius:4,fontSize:11,color:"#a78bfa"}}>{r}</span>
                  ))}
                  <div style={{fontSize:11,color:"#555",marginTop:8,lineHeight:1.6}}>{t.description}</div>
                </div>
              )}
            </div>
          ))}
        </Card>

        <Card title="MCP Resources — Read Side" subtitle="Query endpoints for projections and event streams">
          {resources.resources.map((r,i)=>(
            <div key={i} style={{padding:"10px 12px",borderRadius:6,border:"1px solid #2a2a3a",background:"#0f1117",marginBottom:6}}>
              <div style={{fontSize:13,fontWeight:500,color:"#60a5fa",marginBottom:4}}>{r.uriTemplate||r.uri}</div>
              <div style={{fontSize:11,color:"#555",lineHeight:1.5}}>{r.description}</div>
              <div style={{fontSize:10,color:"#333",marginTop:4}}>{r.name} · {r.mimeType}</div>
            </div>
          ))}
        </Card>
      </div>
    </div>
  )
}
