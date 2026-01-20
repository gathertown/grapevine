import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgPerson = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M15.25 22.25V16.25H16.25C16.8023 16.25 17.25 15.8023 17.25 15.25V11.75C17.25 10.0931 15.9069 8.75 14.25 8.75H9.75C8.09315 8.75 6.75 10.0931 6.75 11.75V15.25C6.75 15.8023 7.19772 16.25 7.75 16.25H8.75V22.25M14.25 4C14.25 5.24264 13.2426 6.25 12 6.25C10.7574 6.25 9.75 5.24264 9.75 4C9.75 2.75736 10.7574 1.75 12 1.75C13.2426 1.75 14.25 2.75736 14.25 4Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgPerson);
export default Memo;