import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgCompose = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M11.25 3.75H8.55C6.86984 3.75 6.02976 3.75 5.38803 4.07698C4.82354 4.3646 4.3646 4.82354 4.07698 5.38803C3.75 6.02976 3.75 6.86984 3.75 8.55V15.45C3.75 17.1302 3.75 17.9702 4.07698 18.612C4.3646 19.1765 4.82354 19.6354 5.38803 19.923C6.02976 20.25 6.86984 20.25 8.55 20.25H15.45C17.1302 20.25 17.9702 20.25 18.612 19.923C19.1765 19.6354 19.6354 19.1765 19.923 18.612C20.25 17.9702 20.25 17.1302 20.25 15.45V12.75M12.75 11.25V8.24998L17.25 3.74998C18.0784 2.92156 19.4216 2.92156 20.25 3.74998C21.0784 4.57841 21.0784 5.92155 20.25 6.74998L15.75 11.25H12.75Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgCompose);
export default Memo;