import {notFound} from "next/navigation";
export default function Layout({children}:{children:React.ReactNode}){if(process.env.ENABLE_COLLECTOR_UI!=="true")notFound();return <>{children}</>}
