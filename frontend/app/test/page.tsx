import {optionalWorkspaceApi} from '@/lib/workspace';
import TestClient from './test-client';
export const dynamic = 'force-dynamic';
export default async function TestPage(){const account=await optionalWorkspaceApi('/v1/account');return <TestClient authenticated={!!account}/>;}
