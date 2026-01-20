import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgMap = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M9 4.99998V17.5M15.5 6.49998V19M3 17.4188V7.58112C3 6.93547 3.41315 6.36226 4.02566 6.15809L8.54397 4.65199C8.84056 4.55312 9.16063 4.5494 9.45944 4.64134L15.0406 6.35861C15.3394 6.45055 15.6594 6.44683 15.956 6.34797L19.5257 5.15809C20.497 4.83433 21.5 5.55728 21.5 6.58112V16.4188C21.5 17.0645 21.0869 17.6377 20.4743 17.8419L15.956 19.348C15.6594 19.4468 15.3394 19.4506 15.0406 19.3586L9.45944 17.6413C9.16063 17.5494 8.84056 17.5531 8.54397 17.652L4.97434 18.8419C4.00305 19.1656 3 18.4427 3 17.4188Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="square" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgMap);
export default Memo;