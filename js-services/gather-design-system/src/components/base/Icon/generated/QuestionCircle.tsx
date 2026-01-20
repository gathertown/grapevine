import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgQuestionCircle = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M12 16V15.99M9.75 9.25C9.75 8.42157 10.4216 7.75 11.25 7.75H12.4587C13.448 7.75 14.25 8.552 14.25 9.54132C14.25 10.1402 13.9507 10.6996 13.4523 11.0318L12.8906 11.4063C12.3342 11.7772 12 12.4017 12 13.0704V13.25M12 21.25C17.1086 21.25 21.25 17.1086 21.25 12C21.25 6.89137 17.1086 2.75 12 2.75C6.89137 2.75 2.75 6.89137 2.75 12C2.75 17.1086 6.89137 21.25 12 21.25ZM12.25 16C12.25 16.1381 12.1381 16.25 12 16.25C11.8619 16.25 11.75 16.1381 11.75 16C11.75 15.8619 11.8619 15.75 12 15.75C12.1381 15.75 12.25 15.8619 12.25 16Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgQuestionCircle);
export default Memo;