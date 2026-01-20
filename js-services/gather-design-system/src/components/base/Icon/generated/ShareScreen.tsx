import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgShareScreen = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M9.8055 11.1978L12.0005 9.11422M12.0005 9.11422L14.1956 11.1978M12.0005 9.11422V14.9256M19.7312 20.0476H4.26978C3.15048 20.0476 2 19.187 2 18.1245V5.87307C2 4.81058 3.15048 3.95001 4.26978 3.95001H19.7302C20.8496 3.95001 22 4.81058 22 5.87307V18.1255C22.001 19.187 20.8496 20.0476 19.7312 20.0476Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgShareScreen);
export default Memo;