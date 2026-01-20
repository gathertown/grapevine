import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgLamp = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M12.5 13L12.5 21" stroke="currentColor" strokeWidth={1.5} /><path d="M16 9.5C16 11.7091 14.433 13.5 12.5 13.5C10.567 13.5 9 11.7091 9 9.5" stroke="currentColor" strokeWidth={1.5} /><path d="M12.5 3C8.91015 3 6 6.13401 6 10H19C19 6.13401 16.0899 3 12.5 3Z" stroke="currentColor" strokeWidth={1.5} /><path d="M10 21H15" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" /></svg>;
const Memo = memo(SvgLamp);
export default Memo;