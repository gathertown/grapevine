import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgCursor = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path fillRule="evenodd" clipRule="evenodd" d="M9.079 19.1789L4.08 5.69394C3.708 4.68894 4.686 3.71094 5.691 4.08294L19.182 9.08594C20.337 9.51394 20.246 11.1759 19.052 11.4759L12.985 12.9999L11.47 19.0479C11.171 20.2429 9.508 20.3349 9.079 19.1789V19.1789Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgCursor);
export default Memo;