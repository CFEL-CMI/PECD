import numpy as np
import h5py
import re
import itertools
from pywigxjpf.pywigxjpf import wig_table_init, wig_temp_init, wig3jj, wig6jj, wig_temp_free, wig_table_free
from wigner.wiglib import DJmk, DJ_m_k, DJ_m_k_2D
import sys
import scipy.interpolate
import random


_weight = None
_max_weight = None


def metropolis(rmin, rmax):
    global _weight, _max_weight
    xmax = 1.0
    xmin = 0.0
    r = []
    for i in range(len(rmin)):
        x = random.uniform(xmin,xmax)
        r.append((x-xmin)*(rmax[i]-rmin[i])/(xmax-xmin)+rmin[i])
    w = _weight(r[0],r[1],r[2])/_max_weight
    eta = random.uniform(0.0,1.0)
    if w>eta:
        rn = r
    else:
        rn = None
    return rn


def euler_rot(chi, theta, phi, xyz):
    """Rotates Cartesian vector xyz[ix] (ix=x,y,z) by an angle phi around Z,
    an angle theta around new Y, and an angle chi around new Z.
    Input values of chi, theta, and phi angles are in radians.
    """
    amat = np.zeros((3,3), dtype=np.float64)
    bmat = np.zeros((3,3), dtype=np.float64)
    cmat = np.zeros((3,3), dtype=np.float64)
    rot = np.zeros((3,3), dtype=np.float64)

    amat[0,:] = [np.cos(chi), np.sin(chi), 0.0]
    amat[1,:] = [-np.sin(chi), np.cos(chi), 0.0]
    amat[2,:] = [0.0, 0.0, 1.0]

    bmat[0,:] = [np.cos(theta), 0.0, -np.sin(theta)]
    bmat[1,:] = [0.0, 1.0, 0.0]
    bmat[2,:] = [np.sin(theta), 0.0, np.cos(theta)]

    cmat[0,:] = [np.cos(phi), np.sin(phi), 0.0]
    cmat[1,:] = [-np.sin(phi), np.cos(phi), 0.0]
    cmat[2,:] = [0.0, 0.0, 1.0]

    rot = np.transpose(np.dot(amat, np.dot(bmat, cmat)))
    xyz_rot = np.dot(rot, xyz)
    return xyz_rot


def monte_carlo(grid, dens, xyz, fname, npoints=100000):
    global _weight, _max_weight
    _weight = scipy.interpolate.NearestNDInterpolator(grid.T, dens)
    _max_weight = np.max(dens)
    fl = open(fname, "w")
    norm = [1 for x in xyz] #[np.linalg.norm(x) for x in xyz]
    npt = 0
    while npt<=npoints:
        euler = metropolis([0,0,0], [2*np.pi,np.pi,2*np.pi])
        if euler is None: continue
        phi = euler[0]
        theta = euler[1]
        chi = euler[2]
        xyz_rot = [euler_rot(chi, theta, phi, x) for x in xyz]
        fl.write( "    ".join(" ".join("%16.12f"%(x[ix]/n) for ix in range(3)) for x,n in zip(xyz_rot,norm)) + "\n")
        npt+=1
    fl.close()


def read_coefficients(coef_file, coef_thresh=1.0e-16):
    """Reads Richmol coefficients file
    """
    print("\nRead Richmol states' coefficients file", coef_file)
    states = []
    fl = open(coef_file, "r")
    for line in fl:
        w = line.split()
        jrot = int(w[0])
        id = int(w[1])
        ideg = int(w[2])
        enr = float(w[3])
        nelem = int(w[4])
        coef = []
        vib = []
        krot = []
        for ielem in range(nelem):
            c = float(w[5+ielem*4])
            im = int(w[6+ielem*4])
            if abs(c)**2<=coef_thresh: continue
            coef.append(c*{0:1,1:1j}[im])
            vib.append(int(w[7+ielem*4]))
            krot.append(int(w[8+ielem*4]))
        states.append({"j":jrot,"id":id,"ideg":ideg,"coef":coef,"v":vib,"k":krot,"enr":enr})
    fl.close()
    return states


def read_wavepacket(coef_file, coef_thresh=1.0e-16):
    """Reads Richmol wavepacket coefficients file
    """
    print("\nRead Richmol wavepacket file", coef_file)
    time = []
    quanta = []
    coefs = []
    h5 = h5py.File(coef_file, mode='r')
    for key in h5.keys():
        st = re.sub(r"results_t_", "", key)
        t = float(re.sub("_", ".", st))
        q = h5[key]["quanta_t_"+st].value
        c = h5[key]["coef_t_"+st].value
        quanta.append(q[abs(c)**2>coef_thresh,:])
        coefs.append(c[abs(c)**2>coef_thresh])
        time.append(t)
    h5.close()
    return time, coefs, quanta


def rotdens(npoints, nbatches, ibatch, states, quanta, coefs):
    """
    """

    # generate 3D grid of Euler angles

    npt = int(npoints**(1/3)) # number of points in 1D
    alpha = list(np.linspace(0, 2*np.pi, num=npt, endpoint=True))
    beta  = list(np.linspace(0, np.pi, num=npt, endpoint=True))
    gamma = list(np.linspace(0, 2*np.pi, num=npt, endpoint=True))
    grid = [alpha, beta, gamma]
    grid_3d = np.array(list(itertools.product(*grid))).T
    npoints_3d = grid_3d.shape[1]
    print("\nTotal number of points in 3D grid of Euler angles:", npoints_3d, "    ", grid_3d.shape)

    # process only smaller batch of points
    npt = int(npoints_3d / nbatches)
    ipoint0 = npt*ibatch
    if ibatch==nbatches-1:
        ipoint1 = npoints_3d
    else:
        ipoint1 = ipoint0 + npt - 1
    npoints_3d = ipoint1 - ipoint0
    print(ibatch, "-batch number of points in 3D grid of Euler angles:", npoints_3d, "[", ipoint0, "-", ipoint1, "]")


    # mapping between wavepacket and rovibrational states

    ind_state = []
    for q in quanta:
        j = q[1]
        id = q[2]
        ideg = q[3]
        istate = [(state["j"],state["id"],state["ideg"]) for state in states].index((j,id,ideg))
        ind_state.append(istate)


    # lists of J and m quantum numbers

    jlist = list(set(j for j in quanta[:,1]))
    mlist = []
    for j in jlist:
        mlist.append(list(set(m  for m,jj in zip(quanta[:,0],quanta[:,1]) if jj==j)))
    print("List of J-quanta:", jlist)
    print("List of m-quanta:", mlist)


    # precompute symmetric-top functions on a 3D grid of Euler angles for given J, m=J, and k=-J..J

    print("\nPrecompute symmetric-top functions...")
    symtop = []
    for J,ml,ij in zip(jlist,mlist,range(len(jlist))):
        print("J = ", J)
        Jfac = np.sqrt((2*J+1)/(8*np.pi**2))
        symtop.append([])
        for m in ml:
            print("m = ", m)
            wig = DJ_m_k(int(J), int(m), grid_3d[:,ipoint0:ipoint1])
            symtop[ij].append( np.conj(wig) * Jfac )
    print("...done")


    # compute rotational density

    vmax = max([max([v for v in state["v"]]) for state in states])
    func = np.zeros((npoints_3d,vmax+1), dtype=np.complex128)
    tot_func = np.zeros((npoints_3d,vmax+1), dtype=np.complex128)
    dens = np.zeros(npoints_3d, dtype=np.complex128)

    for q,cc,istate in zip(quanta,coefs,ind_state):

        m = q[0]
        j = q[1]
        state = states[istate]

        ind_j = jlist.index(j)
        ind_m = mlist[ind_j].index(m)

        # primitive rovibrational function on Euler grid
        func[:,:] = 0
        for v,k,c in zip(state["v"],state["k"],state["coef"]):
            func[:,v] += c * symtop[ind_j][ind_m][:,k+int(j)]

        # total function
        tot_func[:,:] += func[:,:] * cc

    # reduced rotational density on Euler grid
    dens = np.einsum('ij,ji->i', tot_func, np.conj(tot_func.T)) * np.sin(grid_3d[1,ipoint0:ipoint1])

    return grid_3d, dens, [ipoint0,ipoint1]


def rotdens_2D(npoints, states, quanta, coefs):
    """
    """

    # generate 3D grid of Euler angles

    npt = int(npoints**(1/2)) # number of points in 1D
    beta  = list(np.linspace(0, np.pi, num=npt, endpoint=True))
    gamma = list(np.linspace(0, 2*np.pi, num=npt, endpoint=True))
    grid = [beta, gamma]
    grid_2d = np.array(list(itertools.product(*grid))).T
    npoints_2d = grid_2d.shape[1]
    print("\nTotal number of points in 2D grid of Euler angles:", npoints_2d, "    ", grid_2d.shape)

    # mapping between wavepacket and rovibrational states

    ind_state = []
    for q in quanta:
        j = q[1]
        id = q[2]
        ideg = q[3]
        istate = [(state["j"],state["id"],state["ideg"]) for state in states].index((j,id,ideg))
        ind_state.append(istate)


    # lists of J and m quantum numbers

    jlist = list(set(j for j in quanta[:,1]))
    mlist = []
    for j in jlist:
        mlist.append(list(set(m  for m,jj in zip(quanta[:,0],quanta[:,1]) if jj==j)))
    print("List of J-quanta:", jlist)
    print("List of m-quanta:", mlist)
    all_m = sum(mlist, []) # flatten mlist
    print("List of all m-quanta:", all_m)

    # precompute symmetric-top functions on a 3D grid of Euler angles for given J, m, and k=-J..J

    print("\nPrecompute symmetric-top functions...")
    symtop = []
    for J,ml,ij in zip(jlist,mlist,range(len(jlist))):
        print("J = ", J)
        Jfac = np.sqrt((2*J+1)/(8*np.pi**2))
        symtop.append([])
        for m in ml:
            print("m = ", m)
            wig = DJ_m_k_2D(int(J), int(m), grid_2d)
            symtop[ij].append( np.conj(wig) * Jfac )
    print("...done")


    # compute rotational density

    vmax = max([max([v for v in state["v"]]) for state in states])
    mmax_ind = len(all_m)
    try:
        maxispin = np.max(quanta[:,4])
    except:
        maxispin = 0
    func = np.zeros((npoints_2d,vmax+1), dtype=np.complex128)
    tot_func = np.zeros((npoints_2d,vmax+1,mmax_ind,maxispin+1), dtype=np.complex128)
    #dens = np.zeros(npoints_2d, dtype=np.complex128)

    for q,cc,istate in zip(quanta,coefs,ind_state):

        m = q[0]
        j = q[1]
        try:
            ispin = q[4]
        except:
            ispin = 0
        state = states[istate]

        ind_j = jlist.index(j)
        ind_m = mlist[ind_j].index(m)

        # primitive rovibrational function on Euler grid
        func[:,:] = 0
        for v,k,c in zip(state["v"],state["k"],state["coef"]):
            func[:,v] += c * symtop[ind_j][ind_m][:,k+int(j)]

        # total function
        ind_m = all_m.index(m)
        tot_func[:,:,ind_m,ispin] += func[:,:] * cc

    # reduced rotational density on Euler grid
    dens = np.einsum('ijkl,ijkm->ilm', tot_func, np.conj(tot_func)) * 2*np.pi

    return grid_2d, dens



if __name__ == "__main__":

    coef_file = sys.argv[1]
    wavepacket_file = sys.argv[2]
    time0 = round(float(sys.argv[3]),1)
    dens_name = sys.argv[4]

    states = read_coefficients(coef_file, coef_thresh=1.0e-06)
    time, coefs, quanta = read_wavepacket(wavepacket_file, coef_thresh=1.0e-06)

    time_index = [round(t,1) for t in time].index(time0)

    #for t,itime in zip(time,range(len(time))):
    #    print(itime, t)
    #sys.exit()

    # compute rotational density

    for itime in [time_index]:

        print(itime, time[itime])

        npoints = 100000
        nbatches = 1

        # 2d-grid
        grid_2d, dens = rotdens_2D(npoints, states, quanta[itime], coefs[itime])

        fl = open(dens_name, "w")
        for ipoint in range(grid_2d.shape[1]):
            theta = grid_2d[0,ipoint]
            chi = grid_2d[1,ipoint]
            d = dens[ipoint,0,0] * np.sin(theta)
            fl.write( " ".join("%16.8f"%ang for ang in [theta,chi]) + "  %16.8e"%abs(d) + "\n")
        fl.close()
