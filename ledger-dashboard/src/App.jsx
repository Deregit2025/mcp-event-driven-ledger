import { useState } from "react"
import Sidebar from "./components/Sidebar"
import Overview from "./pages/Overview"
import AuditTrail from "./pages/AuditTrail"
import Compliance from "./pages/Compliance"
import Projections from "./pages/Projections"
import Events from "./pages/Events"
import Demos from "./pages/Demos"
import MCPExplorer from "./pages/MCPExplorer"
import Integrity from "./pages/Integrity"
import ApplicationFlow from "./pages/ApplicationFlow"
import LiveQuery from "./pages/LiveQuery"
import Architecture from "./pages/Architecture"

const PAGES = { 
  overview: Overview, 
  flow: ApplicationFlow,
  audit: AuditTrail, 
  compliance: Compliance, 
  projections: Projections, 
  query: LiveQuery,
  events: Events, 
  demos: Demos, 
  mcp: MCPExplorer, 
  integrity: Integrity,
  architecture: Architecture
}
export default function App() {
  const [page, setPage] = useState("architecture")
  const [appId, setAppId] = useState("APEX-TEST-01")
  const Page = PAGES[page] || Architecture
  return (
    <div style={{display:"flex",height:"100vh",overflow:"hidden"}}>
      <Sidebar page={page} setPage={setPage} appId={appId} setAppId={setAppId} />
      <main style={{flex:1,overflow:"auto",padding:"24px"}}>
        <Page appId={appId} />
      </main>
    </div>
  )
}
