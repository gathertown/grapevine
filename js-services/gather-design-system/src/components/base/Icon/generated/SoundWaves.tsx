import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgSoundWaves = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M7.75 3.75V20.25M3.75 9.75V14.25M12 7.75V16.25M16.25 5.75V18.25M20.25 9.75V14.25" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" /></svg>;
const Memo = memo(SvgSoundWaves);
export default Memo;