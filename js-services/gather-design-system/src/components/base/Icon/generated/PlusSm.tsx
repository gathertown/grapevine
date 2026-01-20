import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgPlusSm = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M12 6.75V12M12 12V17.25M12 12H6.75M12 12H17.25" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" /></svg>;
const Memo = memo(SvgPlusSm);
export default Memo;