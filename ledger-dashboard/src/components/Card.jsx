
export function Card({ title, subtitle, children, style, className="" }) {
  return (
    <div className={`glass-card ${className}`} style={{marginBottom:16,...style}}>
      {title && <div className="brand-font" style={{fontSize:16,fontWeight:600,color:"#fff",marginBottom:subtitle?4:16,letterSpacing:"0.02em"}}>{title}</div>}
      {subtitle && <div style={{fontSize:13,color:"var(--muted)",marginBottom:16}}>{subtitle}</div>}
      {children}
    </div>
  )
}

export function Badge({ children, color="purple" }) {
  const colors = {purple:"#a78bfa",green:"#22c55e",amber:"#f59e0b",red:"#ef4444",blue:"#60a5fa",gray:"#555"}
  const bgs = {purple:"#1e1a3a",green:"#0d1f12",amber:"#1c1400",red:"#1a0a0a",blue:"#0a1628",gray:"#1e2030"}
  return (
    <span style={{padding:"2px 10px",borderRadius:5,fontSize:11,fontWeight:500,color:colors[color],background:bgs[color],border:`1px solid ${colors[color]}33`}}>
      {children}
    </span>
  )
}

export function Stat({ value, label, color="#a78bfa" }) {
  return (
    <div style={{textAlign:"center"}}>
      <div style={{fontSize:32,fontWeight:600,color}}>{value}</div>
      <div style={{fontSize:12,color:"#555",marginTop:2}}>{label}</div>
    </div>
  )
}

export function Loading() {
  return <div style={{color:"#555",fontSize:13,padding:20,textAlign:"center"}}>Loading...</div>
}

export function Err({ msg }) {
  return <div style={{color:"#ef4444",fontSize:12,padding:12,background:"#1a0a0a",borderRadius:6,border:"1px solid #ef444433"}}>{msg || "Error loading data"}</div>
}