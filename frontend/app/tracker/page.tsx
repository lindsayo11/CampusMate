import {privateApi} from '@/lib/session-api';
import {PlansWorkspace} from '@/components/plans-workspace';
export default async function Tracker(){const [plans,paths]=await Promise.all([privateApi('/v1/plans'),privateApi('/v1/paths')]);return <PlansWorkspace initial={plans} paths={paths} agentEnabled={process.env.ENABLE_AGENT_UI==='true'}/>} 
