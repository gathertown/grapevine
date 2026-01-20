import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgPopsicle = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M9.75 6.75V12.75M14.25 6.75V12.75M7.75 17.25H16.25C17.3546 17.25 18.25 16.3546 18.25 15.25V6.75C18.25 3.98858 16.0114 1.75 13.25 1.75H10.75C7.98858 1.75 5.75 3.98858 5.75 6.75V15.25C5.75 16.3546 6.64543 17.25 7.75 17.25ZM10.25 17.25H13.75V20.5C13.75 21.4665 12.9665 22.25 12 22.25C11.0335 22.25 10.25 21.4665 10.25 20.5V17.25Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgPopsicle);
export default Memo;